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
  FakeApi(this.challenges, {this.response, this.flashColors = const []}) : super(baseUrl: 'http://x', apiKey: 'k');

  final List<Challenge> challenges;
  final List<Color> flashColors;
  VerifyResult? response;
  String? lastSubjectId;
  String? lastPurpose;
  LivenessConfig? sessionConfig;
  int enrollCalls = 0;
  List<CapturedFrame>? sentFrames;
  List<int>? sentDurations;

  @override
  Future<FaceSession> createSession({String? subjectId, String purpose = ''}) async {
    lastSubjectId = subjectId;
    lastPurpose = purpose;
    return FaceSession(
        id: 's1',
        mode: subjectId == null ? 'liveness' : 'verify',
        clientConfig: sessionConfig,
        challenges: challenges,
        frameKinds: [
          'neutral_start',
          for (var i = 0; i < challenges.length; i++) 'challenge_$i',
          for (var i = 0; i < flashColors.length; i++) 'flash_$i',
          'neutral_end',
        ],
        ttlSeconds: 60,
        flashColors: flashColors,
        flashHoldMs: 450,
      );
  }

  @override
  Future<VerifyResult> verify({
    required String sessionId,
    required List<CapturedFrame> frames,
    required List<int> challengeDurationsMs,
    String? subjectId,
    Map<String, dynamic> client = const {},
  }) async {
    sentFrames = frames;
    sentDurations = challengeDurationsMs;
    return response ?? const VerifyResult(ok: true, reasonCode: 'OK', verificationId: 1);
  }

  @override
  Future<Subject> enroll({
    required String externalId,
    required List<int> photoJpeg,
    String name = '',
    bool replace = false,
  }) async {
    enrollCalls++;
    if (externalId == 'REJECT') throw LumifaceException('POSE_NOT_FRONTAL');
    return Subject(externalId: externalId, name: name, enrollSpoofScore: 0.9);
  }
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
