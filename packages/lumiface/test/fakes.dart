import 'dart:async';
import 'dart:math';
import 'dart:ui';

import 'package:lumiface/lumiface.dart';

class FakeSource implements FaceSignalSource, FrameCapturer {
  final ctrl = StreamController<FaceSignal>.broadcast(sync: true);
  int captures = 0;

  @override
  Stream<FaceSignal> get signals => ctrl.stream;

  @override
  Future<List<int>> captureJpeg() async {
    captures++;
    return [0xFF, 0xD8, captures];
  }

  void emit(FaceSignal s) => ctrl.add(s);
}

class FakeApi extends LumifaceClient {
  FakeApi(this.challenges, {this.response, this.flashColors = const []}) : super(baseUrl: 'http://x');

  final List<Challenge> challenges;
  final List<Color> flashColors;
  VerifyResult? response;
  String? planError;
  String? lastSubjectId;
  String? lastPurpose;
  LivenessConfig? sessionConfig;
  int enrollCalls = 0;

  /// What the controller streamed: frame timestamps and events, in order.
  final List<int> sentFrames = [];
  final List<(StreamEventName, int, int?)> sentEvents = [];
  bool ended = false;
  bool closed = false;

  /// Stands in for the app's backend call; [subjectId] null = liveness session.
  Future<FaceSession> createSession({String? subjectId = 'E001', String purpose = ''}) async {
    lastSubjectId = subjectId;
    lastPurpose = purpose;
    return FaceSession(id: 's1', token: 'tok', mode: subjectId == null ? 'liveness' : 'verify', ttlSeconds: 60);
  }

  @override
  VerifyStream openStream(FaceSession session, {Map<String, dynamic> clientInfo = const {}}) => _FakeStream(this);

  /// The fake token names the subject, like the real one does server-side: `tok:<id>:<name>`.
  @override
  Future<Subject> enroll({required List<int> photoJpeg, required String enrolToken}) async {
    enrollCalls++;
    final parts = enrolToken.split(':');
    if (parts[1] == 'REJECT') throw LumifaceException('POSE_NOT_FRONTAL');
    return Subject(externalId: parts[1], name: parts.length > 2 ? parts[2] : '', enrollSpoofScore: 0.9);
  }
}

class _FakeStream implements VerifyStream {
  _FakeStream(this.api);
  final FakeApi api;

  @override
  Future<StreamPlan> get plan => api.planError != null
      ? Future.error(LumifaceException(api.planError!))
      : Future.value(StreamPlan(challenges: api.challenges, flashColors: api.flashColors, clientConfig: api.sessionConfig));

  @override
  void sendFrame(List<int> jpeg, int tsMs) => api.sentFrames.add(tsMs);

  @override
  void event(StreamEventName name, int tsMs, {int? index}) => api.sentEvents.add((name, tsMs, index));

  @override
  Future<VerifyResult> end() async {
    api.ended = true;
    return api.response ?? const VerifyResult(ok: true, reasonCode: 'OK', verificationId: 1);
  }

  @override
  void close() => api.closed = true;
}

/// A well-framed face with ML Kit-style landmarks. The nose sits in front of
/// the eye plane, so its x shifts with [yaw] like a real head; [flat] models a
/// printed photo or screen rotated in front of the camera (foreshortened, but
/// the nose stays put relative to the eyes).
FaceSignal neutral(
  int ts, {
  double eye = 0.95,
  double smile = 0.05,
  double yaw = 0,
  double pitch = 0,
  bool flat = false,
}) {
  const cx = 0.5, eyeY = 0.45, noseY = 0.55, halfEye = 0.08;
  final rad = yaw * pi / 180;
  final half = halfEye * cos(rad);
  final noseShift = flat ? 0.0 : 0.35 * halfEye * 2 * sin(rad);
  return FaceSignal(
    tsMs: ts,
    faceCount: 1,
    box: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.45),
    eyeOpenLeft: eye,
    eyeOpenRight: eye,
    smile: smile,
    yaw: yaw,
    pitch: pitch,
    nose: Offset(cx + noseShift, noseY),
    leftEye: Offset(cx - half, eyeY),
    rightEye: Offset(cx + half, eyeY),
  );
}
