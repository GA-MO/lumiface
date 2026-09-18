<p align="center">
  <img src="docs/images/logo.svg" width="260" alt="Lumiface">
</p>

<p align="center">
  Self-hosted face verification with active liveness.<br>
  A screen flash and random challenges on the device, two anti-spoof models and ArcFace matching on your server, one policy per project.
</p>

<p align="center">
  <a href="https://github.com/GA-MO/lumiface/actions/workflows/ci.yml"><img src="https://github.com/GA-MO/lumiface/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <a href="https://github.com/GA-MO/lumiface/actions/workflows/pages.yml"><img src="https://github.com/GA-MO/lumiface/actions/workflows/pages.yml/badge.svg" alt="docs"></a>
  <img src="https://img.shields.io/badge/server-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/flutter-iOS%20%C2%B7%20Android%20%C2%B7%20web-02569B" alt="Flutter">
  <img src="https://img.shields.io/badge/react-19-149eca" alt="React 19">
  <img src="https://img.shields.io/badge/license-MIT-000" alt="MIT">
</p>

<p align="center">
  <a href="https://ga-mo.github.io/lumiface/">Docs</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/get-started">Get started</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/concepts">Concepts</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/flutter">Flutter</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/react">React</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/api">API</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/policy-reference">Policy reference</a> ·
  <a href="https://ga-mo.github.io/lumiface/docs/security">Security</a>
</p>

<p align="center">
  <img src="docs/images/home.jpeg" width="820" alt="The docs site: a live demo window running the real React SDK against a stand-in server, next to the state machine log">
</p>

## What it is

A selfie login usually ends at "a face was detected". Lumiface answers two questions instead: **is a real person in front of the camera**, and **is it the person you enrolled**. The device runs a short session (two random challenges, a smile always among them, then three screen-flash colours the server picked) and uploads seven JPEGs. The server re-checks the timing, runs MiniFASNet and a CVPR-2024 anti-spoof gate on every frame, verifies the head pose and the smile, checks that the cheeks reflected the flash colours in order, and matches **every frame** against the enrolled ArcFace embedding. One `POST /v1/sessions/{id}/verify`, one `{ok, reason_code, scores}`.

Faces never leave your network. The server is a FastAPI app with SQLite or Postgres; the models run on CPU. Every project has an API key and a **policy**, a preset plus overrides for every threshold, changed through the API without a redeploy or an app update.

## Features

- **Identity, not only liveness.** With a `subjectId` the server computes the cosine similarity of every frame against the enrolled face (ArcFace, InsightFace buffalo_l: 99.52% on LFW, EER 0.83%) and fails with `NO_MATCH` when any frame is under `match_threshold`; frames must also match each other (`INCONSISTENT`). Without a `subjectId` the same session is a liveness check.
- **Active liveness on the device.** ML Kit (iOS, Android) or MediaPipe (web) drives blink, turn, nod and smile with timing checks and nose parallax, so a flat photo turning in front of the camera fails before upload.
- **Screen flash.** Three server-chosen colours; the server correlates the chroma deltas on the face with the sequence and rejects when the background reflected as much as the face.
- **Two anti-spoof models.** MiniFASNet for prints and screens, the CVPR-2024 ResNet50 gate for bezel-free replay, on every frame.
- **One policy per project.** `balanced`, `strict`, `relaxed`, `emulator` presets plus per-threshold overrides through `PUT /v1/policy`; the session carries the client tunables, so apps follow the policy without a rebuild.
- **Three flows, two SDKs.** `verify`, `liveness`, `enroll` from Flutter (`FaceVerifyView`) or React (`LumifaceView`), both with a headless controller, themes, and strings in English and Thai.
- **Every code documented.** `TIMING_TOO_FAST`, `SPOOF`, `FLASH_FAIL`, `NO_MATCH`, ... each with who raises it and what the user should do. See [reason codes](https://ga-mo.github.io/lumiface/docs/reason-codes).

## Quick start

Run the server, enrol one face, verify it. [Get started](https://ga-mo.github.io/lumiface/docs/get-started) walks through the same steps with the example app and the React demo.

```bash
cd server
uv sync && uv run python weights/download.py       # buffalo_l (~300MB) + MiniFASNet
cp .env.example .env                               # BOOTSTRAP_API_KEY, ADMIN_API_KEY
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
# enrol a reference photo (one frontal face; a bad photo is rejected with a reason_code)
curl -X POST localhost:8000/v1/subjects -H "X-API-Key: change-me" \
  -F external_id=E001 -F name="Person A" -F photo=@me.jpg

# pick a preset for this project
curl -X PUT localhost:8000/v1/policy -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" -d '{"preset": "balanced"}'
```

```dart
// Flutter: pubspec.yaml → dependencies: lumiface: { path: packages/lumiface }
final client = LumifaceClient(baseUrl: 'http://<lan-ip>:8000', apiKey: 'change-me');

FaceVerifyView(
  client: client,
  subjectId: 'E001',            // omit for liveness only, or flow: FaceFlow.enroll
  purpose: 'checkin',
  strings: LivenessStrings.th,
  onResult: (r) => print('${r.ok} ${r.reasonCode} ${r.scores.match}'),
);
```

```tsx
// React: "@lumiface/react": "github:GA-MO/lumiface#path:packages/lumiface-react"
import { LumifaceClient, LumifaceView, TH } from "@lumiface/react";

const client = new LumifaceClient({ baseUrl: "http://<lan-ip>:8000", apiKey: "change-me" });

<LumifaceView client={client} subjectId="E001" purpose="login" strings={TH}
  onResult={(r) => (r.ok ? signIn(r.verificationId) : toast(r.reasonCode))} />
```

The answer is the same from every client:

```json
{ "ok": true, "mode": "verify", "reason_code": "OK",
  "scores": { "match": 0.71, "spoof": 0.93, "consistency": 0.88 }, "verification_id": 42 }
```

`scores.match` is the lowest cosine similarity across the seven frames against the enrolled face; it is `null` in liveness mode because there is nothing to match against.

## Enrol → verify

| Step | Who | What happens |
|---|---|---|
| **Enrol** | `POST /v1/subjects` with a photo, or `FaceFlow.enroll` from the camera | One frontal face, anti-spoof checked, stored as a 512-d ArcFace embedding under `external_id`. A second photo with `replace` updates it. |
| **Session** | `POST /v1/sessions` (the SDK does this) | The server picks the challenges and flash colours, stamps a TTL and returns the project's client tunables. |
| **Challenge** | on the device | Blink / turn / nod / smile with timing and parallax checks, then the flash; a frame is captured per step. |
| **Verify** | `POST /v1/sessions/{id}/verify` with seven JPEGs | Timing → face → anti-spoof → pose and smile → flash → **match against `E001`** → consistency. The first failing check names the `reason_code`. |

The live demo on the docs home runs `liveness` against a stand-in server because there is no enrolled subject in the browser; the example app and the React demo run all three flows against a real server.

## Examples

| | What it shows | Open |
|---|---|---|
| **Flutter example** | Use cases (check-in, login, enrol, liveness), a subjects tab, history with scores, a preset picker; phone, Android emulator or Chrome | [source](packages/lumiface/example) · [web](https://ga-mo.github.io/lumiface/docs/flutter/web) |
| **React demo** (Vite) | `LumifaceView` with themes and strings, the `useLumiface` hook and the headless controller | `bun run dev:react` → http://localhost:3010 · [source](packages/lumiface-react/demo) |
| **Docs site** | Guides, policy reference, reason codes, and a live demo of the real SDK with a stand-in server | `bun run dev:site` → http://localhost:3002 · [source](website) |

<p align="center">
  <img src="docs/images/flow.jpeg" width="820" alt="Three calls, one result: the device runs the challenges and the flash, the server runs MiniFASNet, the CVPR-2024 gate, the flash check and the ArcFace match">
</p>

## How it works

```
  device (Flutter / React)                          server (FastAPI)
  ────────────────────────                          ────────────────
  POST /v1/sessions ─────────────────────────────▶  pick 2 challenges (smile always) + 3 flash colours,
    ◀──────── challenges, colours, client_config      TTL, project policy tunables
  ML Kit / MediaPipe
    blink · turn · nod · smile  (timing, parallax)
    flash ×3, one frame per step
  POST /v1/sessions/{id}/verify  7 JPEGs ───────▶  timing        FRAME_*, TIMING_*
                                                    face          NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL
                                                    anti-spoof    MiniFASNet + CVPR-2024 gate  → SPOOF
                                                    pose / smile  POSE_MISMATCH, EXPRESSION_MISMATCH
                                                    flash         chroma vs colours, locality → FLASH_FAIL
                                                    identity      cosine(frame, enrolled) ≥ match_threshold → NO_MATCH
                                                    consistency   frames vs each other → INCONSISTENT
    ◀──────── {ok, reason_code, scores, verification_id}
```

Thresholds live in the policy (`match_threshold` 0.45 for `balanced`, 0.55 for `strict`, 0.40 for `relaxed`, ...); every one is listed with its default and meaning in the [policy reference](https://ga-mo.github.io/lumiface/docs/policy-reference). What the pipeline does not stop (latex and silicone masks past the smile, real-time deepfakes injected as a camera) is on the [security page](https://ga-mo.github.io/lumiface/docs/security). Lumiface is not certified liveness (no ISO 30107-3).

## Entry points

| | |
|---|---|
| `server/` | FastAPI: `app/routers` (subjects, sessions, verifications, policy, projects), `app/services` (face, antispoof, flash, expression, verify), `app/policy.py` (presets and schema) |
| `packages/lumiface/` | Flutter: `FaceVerifyView`, `FaceVerifyController`, `LumifaceClient`, `LivenessStrings`, `FaceVerifyTheme`; `example/` app |
| `packages/lumiface-react/` | React: `LumifaceView`, `useLumiface`, headless controller, MediaPipe source; `@lumiface/react/core` is browser-free |
| `website/` | Docs (fumadocs + React Router), builds to `pages-site/` for GitHub Pages |
| `docs/plans/face-check-in.md` | Plan, status and the Android emulator setup |

## Working on it

```bash
cd server && uv run pytest -q                              # server
cd packages/lumiface && flutter analyze && flutter test    # Flutter package
bun install && bun run typecheck && bun run test:react     # React SDK + website
cd packages/lumiface/example && flutter run -d <device>    # or -d chrome
bun run build:pages                                        # static docs into pages-site/
```

`server/scripts/calibrate.py` prints score distributions for a folder of real and attack captures; `eval_videos.py` runs the pipeline over attack videos; `eval_lfw.py` scores the matcher on LFW (99.52% 10-fold, EER 0.83%, no impostor pair above cosine 0.23; see [calibration](https://ga-mo.github.io/lumiface/docs/server/calibration)). Android emulator with the Mac webcam: AVD `face_test`, server at `http://10.0.2.2:8000`, preset `emulator`.
