/// Face verification with active liveness for Flutter (iOS, Android, web).
///
/// Quick start:
/// ```dart
/// final client = FacegateClient(baseUrl: 'https://host:8000', apiKey: 'key');
/// FaceVerifyView(client: client, subjectId: 'E001', purpose: 'checkin',
///   strings: LivenessStrings.th, onResult: (r) => print(r.reasonCode));
/// ```
/// Leave `subjectId` out for a liveness-only check, pass `flow: FaceFlow.enroll`
/// to enrol from the camera, or drive [FaceVerifyController] yourself for a
/// fully custom UI.
library;

export 'src/api/facegate_client.dart';
export 'src/camera/camera_factory.dart';
export 'src/camera/camera_source.dart';
export 'src/camera/image_convert.dart' show RawFrame, rawFrameToJpeg;
export 'src/liveness/challenge_detector.dart';
export 'src/liveness/config.dart';
export 'src/liveness/face_verify_controller.dart';
export 'src/liveness/signal_source.dart';
export 'src/models.dart';
export 'src/ui/face_verify_view.dart';
export 'src/ui/strings.dart';
export 'src/ui/theme.dart';
