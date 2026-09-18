import 'dart:async';
import 'dart:math';
import 'dart:ui';

import 'package:face_checkin/face_checkin.dart';

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

class FakeApi extends CheckinApi {
  FakeApi(this.challenges, {this.response, this.flashColors = const []}) : super(baseUrl: 'http://x', apiKey: 'k');

  final List<Challenge> challenges;
  final List<Color> flashColors;
  CheckinResult? response;
  List<CapturedFrame>? sentFrames;
  List<int>? sentDurations;

  @override
  Future<CheckinSession> createSession({String? employeeId}) async => CheckinSession(
        id: 's1',
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

  @override
  Future<CheckinResult> verify({
    required String sessionId,
    required String employeeId,
    required List<CapturedFrame> frames,
    required List<int> challengeDurationsMs,
    Map<String, dynamic> client = const {},
  }) async {
    sentFrames = frames;
    sentDurations = challengeDurationsMs;
    return response ?? const CheckinResult(ok: true, reasonCode: 'OK', checkinId: 1);
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
