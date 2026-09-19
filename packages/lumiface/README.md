# lumiface

Face verification with active liveness for Flutter (iOS, Android, web), backed by the Lumiface server.

```dart
final client = LumifaceClient(baseUrl: 'https://faces.example.com');   // holds no secret

FaceVerifyView(
  client: client,
  sessionProvider: () async => FaceSession.fromJson(await myBackend.createFaceSession('E001')),
  strings: LivenessStrings.th,
  theme: FaceVerifyTheme.fromScheme(Theme.of(context).colorScheme),
  onResult: (r) => print('${r.ok} ${r.reasonCode}'),
);
```

- `FaceVerifyView`: camera + flow with a default overlay; `theme`, `strings`, `promptBuilder`, `progressBuilder`, `resultBuilder`, `flashBuilder` or `overlayBuilder` for your own UI.
- `FaceVerifyController`: the headless state machine; feed any `FaceSignalSource` + `VideoRecorder`.
- `LumifaceClient`: the device side — streams a session's recording with the token your backend hands it through `sessionProvider`. It cannot take the project key; your backend creates the session with the person's photo as `reference_photo` (or none, for liveness) and the server keeps nothing between sessions.
- No backend client on purpose: the key's side is REST from your backend (`POST /v1/sessions`, `GET /v1/sessions/{id}`); `examples/backend` in the repository is a complete one.
- `LivenessConfig` follows the project's policy (`client_config` in every session) unless you pass one.

Device tests of the encoders (no camera needed): `cd examples/flutter/android && ./gradlew :lumiface:connectedDebugAndroidTest`
runs the MediaCodec path on an attached phone or emulator (`android/src/androidTest`), `xcodebuild test -workspace
examples/flutter/ios/Runner.xcworkspace -scheme Runner -destination id=<udid> -only-testing:RunnerTests` the VideoToolbox
path on an iPhone; both write the access units to the app's files for `server/scripts/check_h264.py`.

Docs: `website/content/docs/flutter`. Example app: `examples/flutter` in the repository.

The stream the server judges is H.264 video from the platform encoder (MediaCodec, VideoToolbox), ~30 fps, cut into one access unit per message; on the web MediaRecorder's WebM (Safari: MP4). Detectors: iOS uses Apple Vision (`ios/`, `VNDetectFaceRectanglesRequest`, box plus yaw and pitch), Android TensorFlow Lite BlazeFace bundled in `android/` (box only, with the R8 keep rules; test on a phone with `--release`, debug builds hide R8 problems), the web TensorFlow.js BlazeFace loaded from jsDelivr by the package asset `assets/lumiface_blazeface.js` with the model in `assets/face_detection_short/`; pass `BlazeFaceCameraSource(tfjsUrl:, wasmUrl:, modelUrl:)` through `sourceFactory` to self-host. iOS: `NSCameraUsageDescription`, platform ≥ 15.5. Android: minSdk ≥ 23.
