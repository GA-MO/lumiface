/// Face verification with active liveness for Flutter (iOS, Android, web).
///
/// Quick start:
/// ```dart
/// final client = LumifaceClient(baseUrl: 'https://host:8000');   // no secret on the device
/// FaceVerifyView(
///   client: client,
///   sessionProvider: () async => FaceSession.fromJson(await myApi.createFaceSession('E001')),
///   strings: LivenessStrings.th,
///   onResult: (r) => print(r.reasonCode),
/// );
/// ```
/// Your backend creates the session with the project key over plain REST
/// (`POST /v1/sessions`) and reads the outcome (`GET /v1/sessions/{id}`); see
/// `examples/backend` in the repository.
/// Pass `flow: FaceFlow.enroll` with an `enrolTokenProvider` to enrol from the
/// camera, or drive [FaceVerifyController] yourself for a fully custom UI.
library;

export 'src/api/lumiface_client.dart';
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
