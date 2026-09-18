import 'dart:async';
import 'dart:math';
import 'dart:ui' show Color;

import 'package:flutter/foundation.dart';

import '../api/checkin_api.dart';
import '../models.dart';
import 'challenge_detector.dart';
import 'config.dart';
import 'signal_source.dart';

enum LivenessPhase { idle, starting, aligning, challenge, flash, uploading, success, failed }

enum AlignHint { noFace, multipleFaces, tooFar, tooClose, notCentered, lookStraight, holdStill }

@immutable
class LivenessState {
  const LivenessState({
    this.phase = LivenessPhase.idle,
    this.hint,
    this.challenge,
    this.challengeIndex = 0,
    this.challengeCount = 0,
    this.flashColor,
    this.flashIndex = 0,
    this.result,
  });

  final LivenessPhase phase;
  final AlignHint? hint;
  final Challenge? challenge;
  final int challengeIndex;
  final int challengeCount;

  /// Colour the UI must fill the whole screen with while [phase] is [LivenessPhase.flash].
  final Color? flashColor;
  final int flashIndex;
  final CheckinResult? result;

  LivenessState copyWith({
    LivenessPhase? phase,
    AlignHint? hint,
    bool clearHint = false,
    Challenge? challenge,
    int? challengeIndex,
    int? challengeCount,
    Color? flashColor,
    bool clearFlash = false,
    int? flashIndex,
    CheckinResult? result,
  }) =>
      LivenessState(
        phase: phase ?? this.phase,
        hint: clearHint ? null : (hint ?? this.hint),
        challenge: challenge ?? this.challenge,
        challengeIndex: challengeIndex ?? this.challengeIndex,
        challengeCount: challengeCount ?? this.challengeCount,
        flashColor: clearFlash ? null : (flashColor ?? this.flashColor),
        flashIndex: flashIndex ?? this.flashIndex,
        result: result ?? this.result,
      );

  bool get isDone => phase == LivenessPhase.success || phase == LivenessPhase.failed;
}

/// Drives one check-in: session -> align -> challenges -> screen flash -> upload.
///
/// The flash step shows each server-picked colour for [CheckinSession.flashHoldMs]
/// and uploads one frame per colour; the server checks that the face reflected
/// the sequence (a screen replay reflects nothing, a recording cannot know it).
///
/// When the server picked no turn challenge and [LivenessConfig.parallaxWhenNoTurn]
/// is set, a client-only turn is appended so the nose-parallax check always
/// runs; it captures no frame and reports no duration to the server.
///
/// All timing is derived from [FaceSignal.tsMs] so the controller is fully
/// deterministic under test; a wall-clock watchdog only guards against the
/// signal stream stalling.
class LivenessController {
  LivenessController({
    required this.source,
    required this.capturer,
    required this.api,
    required this.employeeId,
    this.config = const LivenessConfig(),
    this.clientInfo = const {},
  });

  final FaceSignalSource source;
  final FrameCapturer capturer;
  final CheckinApi api;
  final String employeeId;
  final LivenessConfig config;
  final Map<String, dynamic> clientInfo;

  final ValueNotifier<LivenessState> state = ValueNotifier(const LivenessState());

  CheckinSession? _session;
  List<Challenge> _plan = const [];
  StreamSubscription<FaceSignal>? _sub;
  Timer? _watchdog;
  bool _disposed = false;
  bool _busy = false;

  final List<CapturedFrame> _frames = [];
  final List<int> _durations = [];
  int? _alignedSince;
  int? _challengeStartedAt;
  int? _lastFaceSeenAt;
  int? _settleUntil;
  int? _flashStartedAt;
  bool _flashDone = false;
  ChallengeDetector? _detector;

  Future<void> start() async {
    if (state.value.phase != LivenessPhase.idle) return;
    _set(state.value.copyWith(phase: LivenessPhase.starting));
    try {
      _session = await api.createSession(employeeId: employeeId);
    } catch (e) {
      _finish(CheckinResult.clientError('NETWORK_ERROR', e.toString()));
      return;
    }
    if (_disposed) return;
    _plan = _planChallenges(_session!.challenges);
    _set(LivenessState(
      phase: LivenessPhase.aligning,
      hint: AlignHint.noFace,
      challengeCount: _plan.length,
    ));
    _armWatchdog(Duration(seconds: _session!.ttlSeconds));
    _sub = source.signals.listen(_onSignal);
  }

  void cancel() => _finish(CheckinResult.clientError('CANCELLED'));

  List<Challenge> _planChallenges(List<Challenge> server) {
    final hasTurn = server.any((c) => c == Challenge.turnLeft || c == Challenge.turnRight);
    if (hasTurn || !config.parallaxWhenNoTurn || config.parallaxMinShift <= 0) return server;
    return [...server, Random().nextBool() ? Challenge.turnLeft : Challenge.turnRight];
  }

  bool _isServerChallenge(int i) => i < _session!.challenges.length;

  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _watchdog?.cancel();
    state.dispose();
  }

  void _armWatchdog(Duration d) {
    _watchdog?.cancel();
    _watchdog = Timer(d, () => _finish(CheckinResult.clientError('TIMEOUT')));
  }

  void _set(LivenessState s) {
    if (!_disposed) state.value = s;
  }

  void _finish(CheckinResult r) {
    if (_disposed || state.value.isDone) return;
    _sub?.cancel();
    _watchdog?.cancel();
    _set(state.value.copyWith(phase: r.ok ? LivenessPhase.success : LivenessPhase.failed, result: r, clearHint: true));
  }

  Future<void> _onSignal(FaceSignal s) async {
    if (_busy || _disposed || state.value.isDone) return;
    final st = state.value;
    if (s.present) _lastFaceSeenAt = s.tsMs;

    switch (st.phase) {
      case LivenessPhase.aligning:
        _align(s);
      case LivenessPhase.challenge:
        await _challenge(s);
      case LivenessPhase.flash:
        _flash(s);
      default:
        break;
    }
  }

  AlignHint? _alignHint(FaceSignal s) {
    if (s.faceCount == 0 || s.box == null) return AlignHint.noFace;
    if (s.faceCount > 1) return AlignHint.multipleFaces;
    final b = s.box!;
    if (b.width < config.minFaceWidthFraction) return AlignHint.tooFar;
    if (b.width > config.maxFaceWidthFraction) return AlignHint.tooClose;
    final dx = (b.center.dx - 0.5).abs();
    final dy = (b.center.dy - 0.5).abs();
    if (dx > config.centerTolerance || dy > config.centerTolerance) return AlignHint.notCentered;
    if ((s.yaw ?? 0).abs() > config.neutralMaxYaw || (s.pitch ?? 0).abs() > config.neutralMaxPitch) {
      return AlignHint.lookStraight;
    }
    return null;
  }

  void _align(FaceSignal s) {
    final hint = _alignHint(s);
    if (hint != null) {
      _alignedSince = null;
      _set(state.value.copyWith(hint: hint));
      return;
    }
    _alignedSince ??= s.tsMs;
    _set(state.value.copyWith(hint: AlignHint.holdStill));
    if (s.tsMs - _alignedSince! >= config.alignHoldMs) {
      _guard(() async {
        await _capture('neutral_start', s.tsMs);
        _startChallenge(0, s);
      });
    }
  }

  /// [s] is the frame that ended alignment / the settle window; detectors get
  /// it as their first sample so a frontal baseline is always seen.
  void _startChallenge(int i, FaceSignal s) {
    final c = _plan[i];
    _detector = ChallengeDetector.forChallenge(c, config)..feed(s);
    _challengeStartedAt = s.tsMs;
    _settleUntil = null;
    _set(state.value.copyWith(
      phase: LivenessPhase.challenge,
      challenge: c,
      challengeIndex: i,
      clearHint: true,
    ));
  }

  Future<void> _challenge(FaceSignal s) async {
    if (!s.present) {
      if (_lastFaceSeenAt != null && s.tsMs - _lastFaceSeenAt! > config.faceLostGraceMs) {
        _finish(CheckinResult.clientError('FACE_LOST'));
      }
      return;
    }
    if (s.faceCount > 1) return;
    if (s.tsMs - _challengeStartedAt! > config.challengeTimeoutMs) {
      _finish(CheckinResult.clientError('TIMEOUT'));
      return;
    }
    if (_settleUntil != null) {
      if (s.tsMs < _settleUntil!) return;
      final next = state.value.challengeIndex + 1;
      if (next < _plan.length) {
        _startChallenge(next, s);
        return;
      }
      // Last frame must be frontal again so every frame matches the enrolment.
      final hint = _alignHint(s);
      if (hint != null) {
        _set(state.value.copyWith(hint: hint));
        return;
      }
      if (!_flashDone && _session!.flashColors.isNotEmpty) {
        _startFlash(0, s.tsMs);
        return;
      }
      _guard(() async {
        await _capture('neutral_end', s.tsMs);
        await _upload();
      });
      return;
    }
    if (_detector!.feed(s)) {
      final i = state.value.challengeIndex;
      if (!_isServerChallenge(i)) {
        _settleUntil = s.tsMs + config.settleAfterChallengeMs;
        return;
      }
      _durations.add(s.tsMs - _challengeStartedAt!);
      _guard(() async {
        await _capture('challenge_$i', s.tsMs);
        _settleUntil = s.tsMs + config.settleAfterChallengeMs;
      });
    }
  }

  void _startFlash(int i, int tsMs) {
    _flashStartedAt = tsMs;
    _set(state.value.copyWith(
      phase: LivenessPhase.flash,
      flashIndex: i,
      flashColor: _session!.flashColors[i],
      clearHint: true,
    ));
  }

  void _flash(FaceSignal s) {
    if (!s.present) {
      if (_lastFaceSeenAt != null && s.tsMs - _lastFaceSeenAt! > config.faceLostGraceMs) {
        _finish(CheckinResult.clientError('FACE_LOST'));
      }
      return;
    }
    if (s.tsMs - _flashStartedAt! < _session!.flashHoldMs) return;
    final i = state.value.flashIndex;
    _guard(() async {
      await _capture('flash_$i', s.tsMs);
      if (i + 1 < _session!.flashColors.length) {
        _startFlash(i + 1, s.tsMs);
        return;
      }
      _flashDone = true;
      _challengeStartedAt = s.tsMs;
      _settleUntil = s.tsMs + config.settleAfterFlashMs;
      _set(state.value.copyWith(phase: LivenessPhase.challenge, clearFlash: true));
    });
  }

  Future<void> _capture(String kind, int tsMs) async {
    final jpeg = await capturer.captureJpeg();
    _frames.add(CapturedFrame(kind: kind, tsMs: tsMs, jpeg: jpeg));
  }

  Future<void> _upload() async {
    _sub?.cancel();
    _set(state.value.copyWith(phase: LivenessPhase.uploading, clearHint: true));
    try {
      final r = await api.verify(
        sessionId: _session!.id,
        employeeId: employeeId,
        frames: _frames,
        challengeDurationsMs: _durations,
        client: clientInfo,
      );
      _finish(r);
    } catch (e) {
      _finish(CheckinResult.clientError('NETWORK_ERROR', e.toString()));
    }
  }

  /// Serialises async work (capture/upload) so signals arriving meanwhile are dropped.
  void _guard(Future<void> Function() body) {
    _busy = true;
    body().catchError((Object e) {
      _finish(CheckinResult.clientError('CAPTURE_ERROR', e.toString()));
    }).whenComplete(() => _busy = false);
  }
}
