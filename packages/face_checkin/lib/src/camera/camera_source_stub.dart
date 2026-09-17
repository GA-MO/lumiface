import 'package:camera/camera.dart';

import '../models.dart';
import 'camera_source.dart';

/// Placeholder for platforms without ML Kit (web). The MediaPipe source lands
/// in a later phase; until then check-in is mobile only.
class MlKitCameraSource implements CameraFaceSource {
  MlKitCameraSource({
    CameraLensDirection lensDirection = CameraLensDirection.front,
    ResolutionPreset resolution = ResolutionPreset.medium,
    int jpegQuality = 90,
  });

  Never _unsupported() => throw UnsupportedError('MlKitCameraSource is only available on iOS/Android');

  @override
  CameraController? get controller => null;
  @override
  bool get isInitialized => false;
  @override
  Stream<FaceSignal> get signals => _unsupported();
  @override
  Future<List<int>> captureJpeg() => _unsupported();
  @override
  Future<void> initialize() => _unsupported();
  @override
  Future<void> startStream() => _unsupported();
  @override
  Future<void> stopStream() => _unsupported();
  @override
  Future<void> dispose() async {}
}
