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
- `FaceVerifyController` / `FaceEnrollController`: the headless state machines; feed any `FaceSignalSource` + `FrameCapturer`.
- `LumifaceClient`: the device side — uploads a session's frames or one enrolment photo, with tokens your backend hands it through `sessionProvider` / `enrolTokenProvider`. It cannot take the project key.
- No backend client on purpose: the key's side is REST from your backend (`POST /v1/sessions`, `GET /v1/sessions/{id}`); `examples/backend` in the repository is a complete one.
- `LivenessConfig` follows the project's policy (`client_config` in every session) unless you pass one.

Docs: `website/content/docs/flutter`. Example app: `examples/flutter` in the repository.

iOS: `NSCameraUsageDescription`, platform ≥ 15.5. Android: minSdk ≥ 23. Web: MediaPipe tasks-vision is loaded from jsDelivr by the package asset `assets/lumiface_mediapipe.js`; pass `MediaPipeCameraSource(tasksVisionUrl:, modelUrl:)` through `sourceFactory` to self-host.
