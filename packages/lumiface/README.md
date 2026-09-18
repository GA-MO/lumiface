# lumiface

Face verification with active liveness for Flutter (iOS, Android, web), backed by the Lumiface server.

```dart
final client = LumifaceClient(baseUrl: 'https://faces.example.com', apiKey: key);

FaceVerifyView(
  client: client,
  subjectId: 'E001',            // omit for liveness only, flow: FaceFlow.enroll to enrol
  purpose: 'checkin',
  strings: LivenessStrings.th,
  theme: FaceVerifyTheme.fromScheme(Theme.of(context).colorScheme),
  onResult: (r) => print('${r.ok} ${r.reasonCode}'),
);
```

- `FaceVerifyView`: camera + flow with a default overlay; `theme`, `strings`, `promptBuilder`, `progressBuilder`, `resultBuilder`, `flashBuilder` or `overlayBuilder` for your own UI.
- `FaceVerifyController` / `FaceEnrollController`: the headless state machines; feed any `FaceSignalSource` + `FrameCapturer`.
- `LumifaceClient`: sessions, verify, subjects, verifications, policy.
- `LivenessConfig` follows the project's policy (`client_config` in every session) unless you pass one.

Docs: `website/content/docs/flutter`. Example app: `example/`.

iOS: `NSCameraUsageDescription`, platform ≥ 15.5. Android: minSdk ≥ 23. Web: MediaPipe tasks-vision is loaded from jsDelivr by the package asset `assets/lumiface_mediapipe.js`; pass `MediaPipeCameraSource(tasksVisionUrl:, modelUrl:)` through `sourceFactory` to self-host.
