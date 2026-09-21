import 'camera_source.dart';
import 'camera_source_stub.dart'
    if (dart.library.io) 'native_camera_source.dart'
    if (dart.library.js_interop) 'blazeface_camera_source.dart';

/// Picks the camera + face detector for the current platform.
CameraFaceSource createCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    createPlatformCameraFaceSource(facing: facing);
