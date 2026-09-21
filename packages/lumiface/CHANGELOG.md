## 0.4.0

- Enrolment is gone from the server and the SDK: `FaceFlow.enroll`, `FaceEnrollController`, `enrolTokenProvider`, `LumifaceClient.enroll`, `Subject`, `FrameCapturer` / `captureJpeg` and `rawFrameToJpeg` are removed, and `LumifaceClient` needs no HTTP client (the `dio` and `image` dependencies are dropped). Your backend sends the person's photo as `reference_photo` when it creates the session; the server keeps nothing between sessions. `FaceFlow` is `verify | liveness`, `sessionProvider` is required, `FaceVerifyView.onController` hands out a `FaceVerifyController` (the abstract `FaceFlowController` is folded into it), and `VerificationRecord.subjectId` became `reference`.

## 0.3.0

- Box-only detectors: TensorFlow Lite BlazeFace in the Android plugin, Apple Vision in a new iOS plugin, TensorFlow.js BlazeFace on the web (`BlazeFaceCameraSource`). ML Kit and MediaPipe are gone.
- `face_move` (the oval) is the only challenge; blink, smile, turn and nod, the nose parallax and their `LivenessConfig` fields are removed. `FaceSignal` carries a box and, where the detector has them, yaw and pitch.
- The stream carries video: `CameraFaceSource` is a `VideoRecorder` (H.264 from MediaCodec on Android and VideoToolbox on iOS, MediaRecorder on the web), `VerifyStream.sendFrame` became `sendChunk`, `openStream` takes the `format`; `FaceVerifyController` takes `recorder` in place of `capturer` (`FaceEnrollController` keeps `capturer` for the photo).

## 0.2.0

- Renamed from `face_checkin` to `lumiface`; `CheckinApi` → `LumifaceClient`, employees → subjects, check-ins → verifications.
- `FaceVerifyView` replaces `FaceCheckinScreen`: flows (`verify`, `liveness`, `enroll`), `FaceVerifyTheme`, builder slots, `overlayBuilder`, `sourceFactory`, `onStateChanged`, `onController`.
- Headless `FaceVerifyController` (subject optional, `purpose`) and `FaceEnrollController`.
- `LivenessConfig.fromJson` / `toJson`; the session's `client_config` is applied automatically.
- Web support through `MediaPipeCameraSource` (Phase 5).
- `LivenessStrings.copyWith`, `messageFor`, per-flow success lines, more reason codes.

## 0.0.1

- Initial check-in screen with ML Kit, screen flash and parallax.
