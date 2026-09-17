import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/checkin_api.dart';
import '../models.dart';
import 'challenge_detector.dart';
import 'config.dart';
import 'signal_source.dart';

enum LivenessPhase { idle, starting, aligning, challenge, uploading, success, failed }

enum AlignHint { noFace, multipleFaces, tooFar, tooClose, notCentered, lookStraight, holdStill }

@immutable
class LivenessState {
  const LivenessState({
    this.phase = LivenessPhase.idle,
    this.hint,
    this.challenge,
    this.challengeIndex = 0,
    this.challengeCount = 0,
    this.result,
  });

  final LivenessPhase phase;
  final AlignHint? hint;
  final Challenge? challenge;
  final int challengeIndex;
  final int challengeCount;
  final CheckinResult? result;

  LivenessState copyWith({
    LivenessPhase? phase,
    AlignHint? hint,
    bool clearHint = false,
    Challenge? challenge,
    int? challengeIndex,
    int? challengeCount,
    CheckinResult? result,
  }) =>
      LivenessState(
        phase: phase ?? this.phase,
        hint: clearHint ? null : (hint ?? this.hint),
        challenge: challenge ?? this.challenge,
        challengeIndex: challengeIndex ?? this.challengeIndex,
        challengeCount: challengeCount ?? this.challengeCount,
        result: result ?? this.result,
      );

  bool get isDone => phase == LivenessPhase.success || phase == LivenessPhase.failed;
}

/// Drives one check-in: session -> align -> challenges -> upload.
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
    _set(LivenessState(
      phase: LivenessPhase.aligning,
      hint: AlignHint.noFace,
      challengeCount: _session!.challenges.length,
    ));
    _armWatchdog(Duration(seconds: _session!.ttlSeconds));
    _sub = source.signals.listen(_onSignal);
  }

  void cancel() => _finish(CheckinResult.clientError('CANCELLED'));

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
        _startChallenge(0, s.tsMs);
      });
    }
  }

  void _startChallenge(int i, int tsMs) {
    final c = _session!.challenges[i];
    _detector = ChallengeDetector.forChallenge(c, config);
    _challengeStartedAt = tsMs;
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
      if (next < _session!.challenges.length) {
        _startChallenge(next, s.tsMs);
        return;
      }
      // Last frame must be frontal again so every frame matches the enrolment.
      final hint = _alignHint(s);
      if (hint != null) {
        _set(state.value.copyWith(hint: hint));
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
      _durations.add(s.tsMs - _challengeStartedAt!);
      _guard(() async {
        await _capture('challenge_$i', s.tsMs);
        _settleUntil = s.tsMs + config.settleAfterChallengeMs;
      });
    }
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
