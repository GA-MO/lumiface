import 'dart:async';
import 'dart:math';
import 'dart:ui' show Color;

import 'package:flutter/foundation.dart';

import '../api/facegate_client.dart';
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
  final VerifyResult? result;

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
    VerifyResult? result,
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
  bool get isFlashing => phase == LivenessPhase.flash && flashColor != null;

  /// 0..1 progress for a progress bar, null while idle or failed.
  double? get progress => switch (phase) {
        LivenessPhase.aligning => 0,
        LivenessPhase.challenge => challengeCount == 0 ? 0 : (challengeIndex + 0.5) / (challengeCount + 1),
        LivenessPhase.flash || LivenessPhase.uploading => challengeCount / (challengeCount + 1),
        LivenessPhase.success => 1,
        _ => null,
      };
}

/// Headless driver of one camera flow. Owns no widget: feed it a
/// [FaceSignalSource] and a [FrameCapturer] and observe [state].
abstract class FaceFlowController {
  FaceFlowController({required this.source, required this.capturer});

  final FaceSignalSource source;
  final FrameCapturer capturer;
  final ValueNotifier<LivenessState> state = ValueNotifier(const LivenessState());

  FaceFlow get flow;

  /// The config in force; the server's `client_config` once a session exists.
  LivenessConfig get config;

  Future<void> start();

  void cancel();

  @mustCallSuper
  void dispose() => state.dispose();
}

AlignHint? alignHint(FaceSignal s, LivenessConfig config) {
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

/// Drives one verification: session -> align -> challenges -> screen flash -> upload.
///
/// With a [subjectId] the server matches the frames against that subject
/// ([FaceFlow.verify]); without one it only proves liveness ([FaceFlow.liveness]).
///
/// The flash step shows each server-picked colour for [FaceSession.flashHoldMs]
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
class FaceVerifyController extends FaceFlowController {
  FaceVerifyController({
    required super.source,
    required super.capturer,
    required this.client,
    this.subjectId,
    this.purpose = '',
    LivenessConfig? config,
    this.clientInfo = const {},
  }) : _explicitConfig = config;

  final FacegateClient client;
  final String? subjectId;
  final String purpose;
  final Map<String, dynamic> clientInfo;
  final LivenessConfig? _explicitConfig;
  LivenessConfig _config = const LivenessConfig();

  @override
  FaceFlow get flow => subjectId == null ? FaceFlow.liveness : FaceFlow.verify;

  @override
  LivenessConfig get config => _config;

  FaceSession? get session => _session;

  FaceSession? _session;
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

  @override
  Future<void> start() async {
    if (state.value.phase != LivenessPhase.idle) return;
    _set(state.value.copyWith(phase: LivenessPhase.starting));
    try {
      _session = await client.createSession(subjectId: subjectId, purpose: purpose);
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
      return;
    }
    if (_disposed) return;
    _config = _explicitConfig ?? _session!.clientConfig ?? const LivenessConfig();
    _plan = _planChallenges(_session!.challenges);
    _set(LivenessState(
      phase: LivenessPhase.aligning,
      hint: AlignHint.noFace,
      challengeCount: _plan.length,
    ));
    _armWatchdog(Duration(seconds: _session!.ttlSeconds));
    _sub = source.signals.listen(_onSignal);
  }

  @override
  void cancel() => _finish(VerifyResult.clientError('CANCELLED'));

  List<Challenge> _planChallenges(List<Challenge> server) {
    final hasTurn = server.any((c) => c == Challenge.turnLeft || c == Challenge.turnRight);
    if (hasTurn || !config.parallaxWhenNoTurn || config.parallaxMinShift <= 0) return server;
    return [...server, Random().nextBool() ? Challenge.turnLeft : Challenge.turnRight];
  }

  bool _isServerChallenge(int i) => i < _session!.challenges.length;

  @override
  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _watchdog?.cancel();
    super.dispose();
  }

  void _armWatchdog(Duration d) {
    _watchdog?.cancel();
    _watchdog = Timer(d, () => _finish(VerifyResult.clientError('TIMEOUT')));
  }

  void _set(LivenessState s) {
    if (!_disposed) state.value = s;
  }

  void _finish(VerifyResult r) {
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

  void _align(FaceSignal s) {
    final hint = alignHint(s, config);
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
        _finish(VerifyResult.clientError('FACE_LOST'));
      }
      return;
    }
    if (s.faceCount > 1) return;
    if (s.tsMs - _challengeStartedAt! > config.challengeTimeoutMs) {
      _finish(VerifyResult.clientError('TIMEOUT'));
      return;
    }
    if (_settleUntil != null) {
      if (s.tsMs < _settleUntil!) return;
      final next = state.value.challengeIndex + 1;
      if (next < _plan.length) {
        _startChallenge(next, s);
        return;
      }
      final hint = alignHint(s, config);
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
        _finish(VerifyResult.clientError('FACE_LOST'));
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
      final r = await client.verify(
        sessionId: _session!.id,
        subjectId: subjectId,
        frames: _frames,
        challengeDurationsMs: _durations,
        client: clientInfo,
      );
      _finish(r);
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
    }
  }

  void _guard(Future<void> Function() body) {
    _busy = true;
    body().catchError((Object e) {
      _finish(VerifyResult.clientError('CAPTURE_ERROR', e.toString()));
    }).whenComplete(() => _busy = false);
  }
}

/// Aligns the face, captures one frontal frame and enrols it as [externalId].
/// The result carries the created [Subject] on success or the server's
/// rejection code (SPOOF, POSE_NOT_FRONTAL, NO_FACE, ...) on failure.
class FaceEnrollController extends FaceFlowController {
  FaceEnrollController({
    required super.source,
    required super.capturer,
    required this.client,
    required this.externalId,
    this.name = '',
    this.replace = false,
    this.config = const LivenessConfig(),
    this.timeout = const Duration(seconds: 60),
  });

  final FacegateClient client;
  final String externalId;
  final String name;
  final bool replace;
  @override
  final LivenessConfig config;
  final Duration timeout;

  StreamSubscription<FaceSignal>? _sub;
  Timer? _watchdog;
  bool _disposed = false;
  bool _busy = false;
  int? _alignedSince;

  @override
  FaceFlow get flow => FaceFlow.enroll;

  @override
  Future<void> start() async {
    if (state.value.phase != LivenessPhase.idle) return;
    state.value = const LivenessState(phase: LivenessPhase.aligning, hint: AlignHint.noFace);
    _watchdog = Timer(timeout, () => _finish(VerifyResult.clientError('TIMEOUT')));
    _sub = source.signals.listen(_onSignal);
  }

  @override
  void cancel() => _finish(VerifyResult.clientError('CANCELLED'));

  @override
  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _watchdog?.cancel();
    super.dispose();
  }

  void _onSignal(FaceSignal s) {
    if (_busy || _disposed || state.value.phase != LivenessPhase.aligning) return;
    final hint = alignHint(s, config);
    if (hint != null) {
      _alignedSince = null;
      state.value = state.value.copyWith(hint: hint);
      return;
    }
    _alignedSince ??= s.tsMs;
    state.value = state.value.copyWith(hint: AlignHint.holdStill);
    if (s.tsMs - _alignedSince! < config.alignHoldMs) return;
    _busy = true;
    _sub?.cancel();
    state.value = state.value.copyWith(phase: LivenessPhase.uploading, clearHint: true);
    _submit();
  }

  Future<void> _submit() async {
    try {
      final jpeg = await capturer.captureJpeg();
      final subject = await client.enroll(externalId: externalId, name: name, photoJpeg: jpeg, replace: replace);
      _finish(VerifyResult.enrolled(subject));
    } on FacegateException catch (e) {
      _finish(VerifyResult(ok: false, mode: 'enroll', reasonCode: e.reasonCode, message: e.details?.toString()));
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
    }
  }

  void _finish(VerifyResult r) {
    if (_disposed || state.value.isDone) return;
    _sub?.cancel();
    _watchdog?.cancel();
    state.value = state.value.copyWith(phase: r.ok ? LivenessPhase.success : LivenessPhase.failed, result: r, clearHint: true);
  }
}
