import '../models.dart';

/// Streams face observations from a camera. Implementations: BlazeFace (Android, web),
/// Apple Vision (iOS).
abstract class FaceSignalSource {
  Stream<FaceSignal> get signals;
}

/// Grabs the most recent camera frame as JPEG bytes (the enrolment photo).
abstract class FrameCapturer {
  Future<List<int>> captureJpeg();
}

/// What each binary message on the stream carries: a recorder's video chunk (`webm` from
/// MediaRecorder, `mp4` from Safari's, `h264` one access unit per message) or a single JPEG frame.
enum StreamFormat {
  jpeg,
  webm,
  mp4,
  h264;

  String get wire => name;
}

/// Records the camera while a verification runs and hands out chunks as they are cut; `tsMs` is
/// the device time (the signal clock) of the chunk's first frame. The server decodes the stream.
abstract class VideoRecorder {
  StreamFormat get format;
  void startRecording(void Function(List<int> data, int tsMs) onChunk);
  void stopRecording();
}
