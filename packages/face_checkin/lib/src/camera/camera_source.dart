import 'package:camera/camera.dart';

import '../liveness/signal_source.dart';

/// Camera-backed signal source + frame capturer used by [FaceCheckinScreen].
abstract class CameraFaceSource implements FaceSignalSource, FrameCapturer {
  CameraController? get controller;
  bool get isInitialized;
  Future<void> initialize();
  Future<void> startStream();
  Future<void> stopStream();
  Future<void> dispose();
}
