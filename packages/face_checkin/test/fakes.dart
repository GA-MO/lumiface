import 'dart:async';
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
  FakeApi(this.challenges, {this.response}) : super(baseUrl: 'http://x', apiKey: 'k');

  final List<Challenge> challenges;
  CheckinResult? response;
  List<CapturedFrame>? sentFrames;
  List<int>? sentDurations;

  @override
  Future<CheckinSession> createSession({String? employeeId}) async => CheckinSession(
        id: 's1',
        challenges: challenges,
        frameKinds: ['neutral_start', for (var i = 0; i < challenges.length; i++) 'challenge_$i', 'neutral_end'],
        ttlSeconds: 60,
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

/// A well-framed neutral face.
FaceSignal neutral(int ts, {double eye = 0.95, double smile = 0.05, double yaw = 0, double pitch = 0}) => FaceSignal(
      tsMs: ts,
      faceCount: 1,
      box: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.45),
      eyeOpenLeft: eye,
      eyeOpenRight: eye,
      smile: smile,
      yaw: yaw,
      pitch: pitch,
    );
