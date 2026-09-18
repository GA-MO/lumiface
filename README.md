# flutter-face-check-in

Face check-in with liveness for internal use: a reusable Flutter package + a self-hosted Python server.

```
server/                    FastAPI · InsightFace buffalo_l · MiniFASNet anti-spoof · SQLite   (see server/README.md)
packages/face_checkin/     Flutter package: FaceCheckinScreen, LivenessController, CheckinApi
packages/face_checkin/example/   demo app (settings · enroll · check-in · history)
docs/plans/face-check-in.md      plan + status (use /go phase N, /handoff, /ship)
```

## How it works

1. App asks the server for a session; the server picks 2 random challenges (blink / smile / turn / nod).
2. On device, ML Kit face detection drives the challenges with timing checks (a genuine blink lasts 40–600 ms,
   the face must stay in frame, each challenge must take ≥ 300 ms) and captures 4 JPEG frames. A head turn also
   needs real nose parallax from ML Kit landmarks (a rotated flat photo has none); if the server picked no turn,
   the app adds one locally. After the challenges the screen flashes 3 server-chosen colours and one frame per
   colour is uploaded; the server checks the face reflected that sequence (shadow mode until calibrated).
3. Server re-checks timing, runs MiniFASNet anti-spoof on every frame, verifies head pose for turn/nod frames,
   matches every frame against the enrolled ArcFace embedding, and requires the same identity across frames.

Not certified liveness (no ISO 30107-3): stops printed photos and most screen replays, not real-time deepfakes
or 3D masks. See `docs/plans/face-check-in.md` for the research summary and upgrade path (Azure/AWS liveness).

## Run

```bash
# server
cd server && uv sync && uv run python weights/download.py && cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# app (real device; ML Kit + camera do not run in the iOS simulator)
cd packages/face_checkin/example && flutter run -d <device>
# Settings tab -> server URL http://<mac-lan-ip>:8000, api key from .env, then Employees -> enroll from gallery
```

## Test without a phone: Android emulator + Mac webcam

```bash
brew install openjdk@17 && brew install --cask android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@17 ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --install platform-tools "platforms;android-36" "build-tools;36.0.0" \
  emulator "system-images;android-35;google_apis;arm64-v8a"
flutter config --android-sdk "$ANDROID_HOME" --jdk-dir "$JAVA_HOME" && yes | flutter doctor --android-licenses
$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager create avd -n face_test -k "system-images;android-35;google_apis;arm64-v8a" -d pixel_6
$ANDROID_HOME/emulator/emulator -webcam-list          # pick the built-in camera, e.g. webcam1
$ANDROID_HOME/emulator/emulator -avd face_test -camera-front webcam1 -camera-back webcam1 &
cd packages/face_checkin/example && flutter run -d emulator-5554
```

In the app set the server URL to `http://10.0.2.2:8000` (the host machine as seen from the emulator). The emulator
crops the landscape webcam into a portrait frame, so sit centred and close to the Mac camera.
Enrol yourself from the Mac: `imagesnap -w 1.5 /tmp/me.jpg` then POST it to `/v1/employees`.

## Use in another project

```yaml
dependencies:
  face_checkin:
    path: ../flutter-face-check-in/packages/face_checkin   # or a git url
```

```dart
final api = CheckinApi(baseUrl: 'http://host:8000', apiKey: 'key');
FaceCheckinScreen(api: api, employeeId: 'E001', strings: LivenessStrings.th, onResult: (r) { ... });
```

iOS: add `NSCameraUsageDescription`, platform ≥ 15.5. Android: minSdk ≥ 23. Web: not yet (phase 5).

## Licences

InsightFace `buffalo_l` weights are **non-commercial research only**. MiniFASNet weights Apache-2.0. Everything else MIT/Apache.
