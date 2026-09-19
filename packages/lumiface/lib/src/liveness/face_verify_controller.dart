import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show Color, Offset, Rect;

import 'package:flutter/foundation.dart';

import '../api/lumiface_client.dart';
import '../models.dart';
import 'challenge_detector.dart';
import 'config.dart';
import 'signal_source.dart';

enum LivenessPhase { idle, starting, aligning, challenge, flash, uploading, success, failed }


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
    this.target,
  });

  final LivenessPhase phase;
  final AlignHint? hint;
  final Challenge? challenge;
  final int challengeIndex;
  final int challengeCount;

  /// The oval a [Challenge.faceMove] asks the face to fill, as fractions of the preview; the
  /// guide draws it instead of the theme's shape once set.
  final Rect? target;

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
    Rect? target,
  }) => LivenessState(
    phase: phase ?? this.phase,
    hint: clearHint ? null : (hint ?? this.hint),
    challenge: challenge ?? this.challenge,
    challengeIndex: challengeIndex ?? this.challengeIndex,
    challengeCount: challengeCount ?? this.challengeCount,
    flashColor: clearFlash ? null : (flashColor ?? this.flashColor),
    flashIndex: flashIndex ?? this.flashIndex,
    result: result ?? this.result,
    target: target ?? this.target,
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

/// The whole camera frame, in frame-normalised coordinates.
const Rect fullFrame = Rect.fromLTWH(0, 0, 1, 1);

/// The part of a [videoAspect] frame that a `BoxFit.cover` preview shows in a
/// [containerAspect] box. Alignment is judged inside this region so "move
/// closer" means what the person sees, not the raw frame the camera delivers.
Rect visibleRegionFor(double videoAspect, double containerAspect) {
  if (videoAspect <= 0 || containerAspect <= 0 || videoAspect == containerAspect) return fullFrame;
  if (videoAspect > containerAspect) {
    final width = containerAspect / videoAspect;
    return Rect.fromLTWH((1 - width) / 2, 0, width, 1);
  }
  final height = videoAspect / containerAspect;
  return Rect.fromLTWH(0, (1 - height) / 2, 1, height);
}

/// Re-expresses a frame-normalised box relative to [region].
Rect boxInRegion(Rect b, Rect region) => Rect.fromLTWH(
  (b.left - region.left) / region.width,
  (b.top - region.top) / region.height,
  b.width / region.width,
  b.height / region.height,
);

/// [maxWidth] overrides [LivenessConfig.maxFaceWidthFraction]: the controller passes the oval's
/// start width so the walk into the oval always begins from where the person held still,
/// whatever the frame's aspect.
AlignHint? alignHint(FaceSignal s, LivenessConfig config, [Rect region = fullFrame, double? maxWidth]) {
  if (s.faceCount == 0 || s.box == null) return AlignHint.noFace;
  if (s.faceCount > 1) return AlignHint.multipleFaces;
  final b = boxInRegion(s.box!, region);
  if (b.width < config.minFaceWidthFraction) return AlignHint.tooFar;
  if (b.width > (maxWidth ?? config.maxFaceWidthFraction)) return AlignHint.tooClose;
  final dx = (b.center.dx - 0.5).abs();
  final dy = (b.center.dy - 0.5).abs();
  if (dx > config.centerTolerance || dy > config.centerTolerance) return AlignHint.notCentered;
  return frontalHint(s, config);
}

/// After the oval the face is close by design: only its presence and (where the detector reports
/// angles) its pose still matter.
AlignHint? frontalHint(FaceSignal s, LivenessConfig config) {
  if (s.faceCount == 0 || s.box == null) return AlignHint.noFace;
  if (s.faceCount > 1) return AlignHint.multipleFaces;
  if ((s.yaw ?? 0).abs() > config.neutralMaxYaw || (s.pitch ?? 0).abs() > config.neutralMaxPitch) {
    return AlignHint.lookStraight;
  }
  return null;
}

/// Headless driver of one verification, owning no widget: feed it a [FaceSignalSource] and a
/// [VideoRecorder] and observe [state]. Session -> align -> the oval -> screen flash -> verdict.
///
/// The backend that creates the session decides what it proves: with a reference photo the
/// server matches the frames against it ([FaceFlow.verify]); without one it only proves
/// liveness ([FaceFlow.liveness]).
///
/// The flash step shows each server-picked colour for [FaceSession.flashHoldMs]
/// and uploads one frame per colour; the server checks that the face reflected
/// the sequence (a screen replay reflects nothing, a recording cannot know it).
///
/// The recorder runs from the plan to the verdict and its chunks go to the server
/// as they are cut; the events sent at each boundary only tell the server where
/// to look, it decides from the frames it decodes and its own clock. All timing
/// here is derived from [FaceSignal.tsMs] so the controller is fully
/// deterministic under test; a wall-clock watchdog only guards against the
/// signal stream stalling.
class FaceVerifyController {
  FaceVerifyController({
    required this.source,
    required this.recorder,
    required this.client,
    required this.sessionProvider,
    FaceFlow flow = FaceFlow.verify,
    LivenessConfig? config,
    this.clientInfo = const {},
  }) : _explicitConfig = config {
    _flow = flow;
  }

  final FaceSignalSource source;
  final ValueNotifier<LivenessState> state = ValueNotifier(const LivenessState());

  /// What the preview shows of the frame; the view keeps it in step with its layout. See [visibleRegionFor].
  Rect visibleRegion = fullFrame;

  /// The camera frame's width over its height; the view keeps it in step with the source.
  double frameAspect = 0.75;

  final LumifaceClient client;

  /// Records the camera for the server; every [CameraFaceSource] is one.
  final VideoRecorder recorder;

  /// Fetches the session from your backend, which created it with the project
  /// key and fixed who is verified (the reference photo): return `FaceSession.fromJson`
  /// of the server's `POST /v1/sessions` response. The device only ever holds the session's token.
  final Future<FaceSession> Function() sessionProvider;
  final Map<String, dynamic> clientInfo;
  final LivenessConfig? _explicitConfig;
  LivenessConfig _config = const LivenessConfig();
  late FaceFlow _flow;

  /// [FaceFlow.verify] or [FaceFlow.liveness]; the session decides once it arrives.
  FaceFlow get flow => _flow;

  /// The config in force; the server's `client_config` once a session exists.
  LivenessConfig get config => _config;

  FaceSession? get session => _session;

  /// The server's plan once the stream is open.
  StreamPlan? get serverPlan => _serverPlan;

  FaceSession? _session;
  StreamPlan? _serverPlan;
  VerifyStream? _stream;
  List<Challenge> _plan = const [];
  StreamSubscription<FaceSignal>? _sub;
  Timer? _watchdog;
  bool _disposed = false;
  bool _busy = false;
  bool _recording = false;
  int? _alignedSince;
  int? _challengeStartedAt;
  int? _lastFaceSeenAt;
  int? _settleUntil;
  bool _doneReported = false;
  int? _flashStartedAt;
  bool _flashDone = false;
  ChallengeDetector? _detector;

  Future<void> start() async {
    if (state.value.phase != LivenessPhase.idle) return;
    _set(state.value.copyWith(phase: LivenessPhase.starting));
    try {
      _session = await sessionProvider();
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
      return;
    }
    if (_disposed) return;
    _flow = _session!.mode == 'liveness' ? FaceFlow.liveness : FaceFlow.verify;
    try {
      _stream = client.openStream(_session!, clientInfo: clientInfo, format: recorder.format);
      _serverPlan = await _stream!.plan;
    } on LumifaceException catch (e) {
      _finish(VerifyResult.clientError(e.reasonCode, e.details?.toString()));
      return;
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
      return;
    }
    if (_disposed) return;
    _config = _explicitConfig ?? _serverPlan!.clientConfig ?? _session!.clientConfig ?? const LivenessConfig();
    _plan = _serverPlan!.challenges;
    _set(LivenessState(phase: LivenessPhase.aligning, hint: AlignHint.noFace, challengeCount: _plan.length));
    _armWatchdog(Duration(seconds: _session!.ttlSeconds));
    _recording = true;
    recorder.startRecording((data, tsMs) => _stream?.sendChunk(data, tsMs));
    _sub = source.signals.listen(_onSignal);
  }

  void _stopRecording() {
    if (!_recording) return;
    _recording = false;
    recorder.stopRecording();
  }

  void cancel() => _finish(VerifyResult.clientError('CANCELLED'));

  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _stopRecording();
    _watchdog?.cancel();
    _stream?.close();
    state.dispose();
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
    _stopRecording();
    _watchdog?.cancel();
    if (state.value.phase != LivenessPhase.uploading) _stream?.close();
    final result = _session != null && r.sessionId == null ? r.withSession(_session!.id) : r;
    _set(
      state.value.copyWith(
        phase: result.ok ? LivenessPhase.success : LivenessPhase.failed,
        result: result,
        clearHint: true,
      ),
    );
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

  /// The widest a face may be at alignment: the oval's start, when the plan has one.
  double get _alignMaxWidth {
    final oval = _ovalRect;
    final limit = config.maxFaceWidthFraction;
    return oval == null ? limit : math.min(limit, boxInRegion(oval, visibleRegion).width * config.moveStartMaxRatio);
  }

  void _align(FaceSignal s) {
    final hint = alignHint(s, config, visibleRegion, _alignMaxWidth);
    if (hint != null) {
      _alignedSince = null;
      _set(state.value.copyWith(hint: hint));
      return;
    }
    _alignedSince ??= s.tsMs;
    _set(state.value.copyWith(hint: AlignHint.holdStill));
    if (s.tsMs - _alignedSince! >= config.alignHoldMs) {
      _stream?.event(StreamEventName.aligned, s.tsMs);
      _startChallenge(0, s);
    }
  }

  /// The plan's oval in frame-normalised coordinates. Its width is a fraction of the frame's shorter
  /// side (faces scale with it whatever the orientation), so both fractions depend on the aspect.
  Rect? get _ovalRect {
    final o = _serverPlan?.oval;
    if (o == null) return null;
    final landscape = frameAspect > 1;
    final w = landscape ? o.width / frameAspect : o.width;
    final h = landscape ? o.width * o.heightRatio : o.width * o.heightRatio * frameAspect;
    return Rect.fromCenter(center: Offset(o.cx, o.cy), width: w, height: h);
  }

  void _startChallenge(int i, FaceSignal s) {
    final c = _plan[i];
    final oval = c == Challenge.faceMove ? _ovalRect : null;
    _detector = ChallengeDetector.forChallenge(c, config, oval: oval)..feed(s);
    _challengeStartedAt = s.tsMs;
    _settleUntil = null;
    _doneReported = false;
    _set(state.value.copyWith(
      phase: LivenessPhase.challenge,
      challenge: c,
      challengeIndex: i,
      clearHint: true,
      target: oval == null ? null : boxInRegion(oval, visibleRegion),
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
      final i = state.value.challengeIndex;
      if (!_doneReported) {
        _doneReported = true;
        _stream?.event(StreamEventName.challengeDone, s.tsMs, index: i);
      }
      final next = i + 1;
      if (next < _plan.length) {
        _startChallenge(next, s);
        return;
      }
      final hint = frontalHint(s, config);
      if (hint != null) {
        _set(state.value.copyWith(hint: hint));
        return;
      }
      if (!_flashDone && _serverPlan!.flashColors.isNotEmpty) {
        _startFlash(0, s.tsMs);
        return;
      }
      _guard(_upload);
      return;
    }
    // The window closes after the settle, so the frames with the face at rest in the oval are inside it.
    if (_detector!.feed(s)) {
      _settleUntil = s.tsMs + config.settleAfterChallengeMs;
    } else if (_detector case FaceMoveDetector(:final hint)) {
      _set(state.value.copyWith(hint: hint, clearHint: hint == null));
    }
  }

  void _startFlash(int i, int tsMs) {
    _flashStartedAt = tsMs;
    _stream?.event(StreamEventName.flash, tsMs, index: i);
    _set(
      state.value.copyWith(
        phase: LivenessPhase.flash,
        flashIndex: i,
        flashColor: _serverPlan!.flashColors[i],
        clearHint: true,
      ),
    );
  }

  void _flash(FaceSignal s) {
    if (!s.present) {
      if (_lastFaceSeenAt != null && s.tsMs - _lastFaceSeenAt! > config.faceLostGraceMs) {
        _finish(VerifyResult.clientError('FACE_LOST'));
      }
      return;
    }
    if (s.tsMs - _flashStartedAt! < _serverPlan!.flashHoldMs) return;
    final i = state.value.flashIndex;
    if (i + 1 < _serverPlan!.flashColors.length) {
      _startFlash(i + 1, s.tsMs);
      return;
    }
    _stream?.event(StreamEventName.flashEnd, s.tsMs);
    _flashDone = true;
    _challengeStartedAt = s.tsMs;
    _settleUntil = s.tsMs + config.settleAfterFlashMs;
    _set(state.value.copyWith(phase: LivenessPhase.challenge, clearFlash: true));
  }

  Future<void> _upload() async {
    _sub?.cancel();
    _set(state.value.copyWith(phase: LivenessPhase.uploading, clearHint: true));
    _stopRecording();
    try {
      _finish(await _stream!.end());
    } catch (e) {
      _finish(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
    }
  }

  void _guard(Future<void> Function() body) {
    _busy = true;
    body()
        .catchError((Object e) {
          _finish(VerifyResult.clientError('CAPTURE_ERROR', e.toString()));
        })
        .whenComplete(() => _busy = false);
  }
}
