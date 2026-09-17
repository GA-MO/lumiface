import '../models.dart';

/// Streams face observations from a camera. Implementations: ML Kit (mobile),
/// MediaPipe (web, later).
abstract class FaceSignalSource {
  Stream<FaceSignal> get signals;
}

/// Grabs the most recent camera frame as JPEG bytes.
abstract class FrameCapturer {
  Future<List<int>> captureJpeg();
}
