<p align="center"><strong>Facegate</strong></p>

<p align="center">
  Self-hosted face verification with active liveness.<br>
  One FastAPI server, a policy per project, and camera SDKs for Flutter (iOS, Android, web) and React.
</p>

```
server/                    FastAPI · InsightFace buffalo_l · MiniFASNet + CVPR-2024 anti-spoof · screen flash · SQLite/Postgres
packages/facegate/         Flutter package: FaceVerifyView, FaceVerifyController, FacegateClient (ML Kit / MediaPipe)
packages/facegate/example/ demo app: use cases · subjects · history · policy presets
packages/facegate-react/   React SDK: FacegateView, useFacegate, headless controller, MediaPipe source, Vite demo
website/                   docs site (fumadocs + React Router), builds to pages-site/ for GitHub Pages
docs/plans/face-check-in.md plan + status
```

## What it does

1. The app asks the server for a session. The server picks two random challenges (a smile is always one), three flash colours and returns the project's client tunables.
2. On the device, ML Kit (mobile) or MediaPipe (web) drives the challenges with timing checks and nose parallax, captures a frame per step, flashes the screen and uploads seven JPEGs.
3. The server re-checks timing, runs MiniFASNet and the CVPR-2024 gate on every frame, verifies head pose and the smile, checks the flash reflection and its locality, matches every frame against the enrolled ArcFace embedding and requires the same identity across frames.

Flows: **verify** (a subject id), **liveness** (no subject), **enroll** (camera enrolment). Every project has an API key and a **policy**: a preset (`balanced`, `strict`, `relaxed`, `emulator`) plus overrides for every threshold, changed through `PUT /v1/policy` without a redeploy or an app update.

Not certified liveness (no ISO 30107-3): stops prints, screen replays, cut-outs and paper masks; latex and silicone masks only through the smile challenge; not real-time deepfakes injected as a camera.

## Run

```bash
# server
cd server && uv sync && uv run python weights/download.py && cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Flutter example (phone, emulator or Chrome)
cd packages/facegate/example && flutter run -d <device>       # or: flutter run -d chrome

# React demo
bun install && bun run dev:react                              # http://localhost:3010

# docs
bun run dev:site                                              # http://localhost:3002
```

Android emulator with the Mac webcam: see `docs/plans/face-check-in.md` (AVD `face_test`, server at `http://10.0.2.2:8000`, preset `emulator`).

## Use it

```dart
final client = FacegateClient(baseUrl: 'http://host:8000', apiKey: 'key');
FaceVerifyView(client: client, subjectId: 'E001', purpose: 'checkin', strings: LivenessStrings.th, onResult: (r) { ... });
```

```tsx
const client = new FacegateClient({ baseUrl: "http://host:8000", apiKey: "key" });
<FacegateView client={client} subjectId="E001" purpose="login" onResult={(r) => ...} />
```

```bash
curl -X PUT http://host:8000/v1/policy -H "X-API-Key: key" -H "Content-Type: application/json" -d '{"preset":"strict"}'
```

Full documentation, API and the generated policy reference: `website/content/docs` (or the published site).

## Verify

```bash
cd server && uv run pytest -q                         # 53 tests
cd packages/facegate && flutter analyze && flutter test   # 39 tests
bun run typecheck && bun run test:react                # 21 tests
bun run build:pages                                   # pages-site/
```

## Licences

InsightFace `buffalo_l` weights are **non-commercial research only**. MiniFASNet weights Apache-2.0, the CVPR-2024 model MIT, everything else MIT/Apache.
