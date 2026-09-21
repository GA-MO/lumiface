import 'camera_source.dart';

CameraFaceSource createPlatformCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    throw UnsupportedError('lumiface needs iOS, Android or the web');
