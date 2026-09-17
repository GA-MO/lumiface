/// Face check-in with active liveness for Flutter (iOS/Android; web later).
///
/// Quick start:
/// ```dart
/// final api = CheckinApi(baseUrl: 'https://host:8000', apiKey: 'key');
/// Navigator.push(context, MaterialPageRoute(builder: (_) =>
///   FaceCheckinScreen(api: api, employeeId: 'E001', strings: LivenessStrings.th,
///     onResult: (r) => print(r.reasonCode))));
/// ```
library;

export 'src/api/checkin_api.dart';
export 'src/camera/camera_source.dart';
export 'src/camera/camera_source_stub.dart' if (dart.library.io) 'src/camera/mlkit_camera_source.dart';
export 'src/camera/image_convert.dart' show RawFrame, rawFrameToJpeg;
export 'src/liveness/challenge_detector.dart';
export 'src/liveness/config.dart';
export 'src/liveness/liveness_controller.dart';
export 'src/liveness/signal_source.dart';
export 'src/models.dart';
export 'src/ui/face_checkin_screen.dart';
export 'src/ui/strings.dart';
