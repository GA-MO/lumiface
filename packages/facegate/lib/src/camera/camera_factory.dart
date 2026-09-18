import 'camera_source.dart';
import 'camera_source_stub.dart'
    if (dart.library.io) 'mlkit_camera_source.dart'
    if (dart.library.js_interop) 'mediapipe_camera_source.dart';

/// Picks the camera + face detector for the current platform.
CameraFaceSource createCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    createPlatformCameraFaceSource(facing: facing);
