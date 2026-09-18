# Flutter example

Every use case of `lumiface` (check-in, login, liveness only, enrol from the camera, custom overlay), a subjects
tab, a history tab with the scores the backend read, and a preset picker. It talks to `examples/backend`
(which holds the project key) and to the Lumiface server with the tokens the backend hands it.

```bash
bun run dev:backend                       # examples/backend on :8010 (needs the server on :8000)
cd examples/flutter
flutter run -d chrome                     # web: MediaPipe, localhost is a secure context
flutter run -d <android-id> --release     # phone: use --release, debug builds hide R8 problems
```

Settings tab: Lumiface URL, backend URL, subject id, debug bar, Thai strings.

| Device | Lumiface URL | Backend URL |
|---|---|---|
| Android phone over USB | `http://localhost:8000` after `adb reverse tcp:8000 tcp:8000` | `http://localhost:8010` after `adb reverse tcp:8010 tcp:8010` |
| Android emulator | `http://10.0.2.2:8000` (preset `emulator`) | `http://10.0.2.2:8010` |
| iPhone on the same Wi‑Fi (native app) | `http://<mac-ip>:8000` | `http://<mac-ip>:8010` |
| iPhone Safari (`flutter run -d web-server --web-hostname 0.0.0.0 --web-port 3020 --web-tls-cert-path … --web-tls-cert-key-path …`) | `https://<mac-ip>:3010` (the React example's TLS proxy, see get-started) | same |
| Chrome | `http://localhost:8000` | `http://localhost:8010` |

The server's `.env` sets the key (`BOOTSTRAP_API_KEY`); start the backend with the same `LUMIFACE_KEY`.

iPhone: put your Apple team in `ios/Flutter/Local.xcconfig` (git-ignored, `DEVELOPMENT_TEAM = XXXXXXXXXX`; a free
personal team works), enable Developer Mode on the phone, then `flutter run --release -d <udid>`. If Flutter's
launcher stalls after the build, `xcrun devicectl device install app --device <udid> build/ios/iphoneos/Runner.app`
followed by `xcrun devicectl device process launch --device <udid> com.example.faceCheckinExample` does the same.
