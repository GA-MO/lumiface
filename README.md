<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.svg">
    <img src="docs/images/logo-light.svg" width="220" alt="Lumiface">
  </picture>
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

A selfie login usually ends at "a face was detected". Lumiface answers two questions instead: **is a real person in front of the camera**, and **is it the person you enrolled**. The device runs a short session (two random challenges, a smile always among them, then three screen-flash colours the server picked) while streaming JPEG frames over a WebSocket the whole time. The server clocks the session itself, confirms each blink, smile, turn and nod from its own landmarks inside its window, checks that the cheeks reflected the flash colours in order, runs MiniFASNet and a CVPR-2024 anti-spoof gate on the key frames, and matches **every key frame** against the enrolled ArcFace embedding. One stream, one `{ok, reason_code, scores}`.

Faces never leave your network. The server is a FastAPI app with SQLite or Postgres; the models run on CPU. Every project has an API key and a **policy**, a preset plus overrides for every threshold, changed through the API without a redeploy or an app update.

## Features

- **Identity, not only liveness.** With a `subjectId` the server computes the cosine similarity of every frame against the enrolled face (ArcFace, InsightFace buffalo_l: 99.52% on LFW, EER 0.83%) and fails with `NO_MATCH` when any frame is under `match_threshold`; frames must also match each other (`INCONSISTENT`). Without a `subjectId` the same session is a liveness check.
- **Active liveness, guided on the device, judged on the server.** ML Kit (iOS, Android) or MediaPipe (web) guides blink, turn, nod and smile and checks nose parallax, so a flat photo turning in front of the camera fails before upload; the server re-reads every gesture from its own landmarks, so a patched client gains nothing.
- **Screen flash.** Three server-chosen colours; the server correlates the chroma deltas on the face with the sequence and rejects when the background reflected as much as the face.
- **Two anti-spoof models.** MiniFASNet for prints and screens, the CVPR-2024 ResNet50 gate for bezel-free replay, on every key frame.
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

From your backend (the API key never leaves it):

```bash
# enrol a reference photo (one frontal face; a bad photo is rejected with a reason_code)
curl -X POST localhost:8000/v1/subjects -H "X-API-Key: lf_sk_change-me" \
  -F external_id=E001 -F name="Person A" -F photo=@me.jpg

# or let the device enrol from its camera: mint a single-use token and hand it to the app
curl -X POST localhost:8000/v1/subjects/tokens -H "X-API-Key: lf_sk_change-me" \
  -H "Content-Type: application/json" -d '{"external_id": "E001", "name": "Person A"}'

# pick a preset for this project
curl -X PUT localhost:8000/v1/policy -H "X-API-Key: lf_sk_change-me" \
  -H "Content-Type: application/json" -d '{"preset": "balanced"}'
```

```dart
// Flutter: pubspec.yaml → dependencies: lumiface: { path: packages/lumiface }
final client = LumifaceClient(baseUrl: 'https://faces.example.com');

FaceVerifyView(
  client: client,
  // Your backend calls POST /v1/sessions with the API key and returns the JSON.
  sessionProvider: () async => FaceSession.fromJson(await myApi.createFaceSession('E001')),
  strings: LivenessStrings.th,
  onResult: (r) => myApi.faceDone(r.sessionId),   // the backend reads the outcome
);
```

```tsx
// React: "@lumiface/react": "github:GA-MO/lumiface#path:packages/lumiface-react"
import { LumifaceClient, LumifaceView, TH, sessionFromJson } from "@lumiface/react";

const client = new LumifaceClient({ baseUrl: "https://faces.example.com" });

<LumifaceView
  client={client}
  sessionProvider={async () => sessionFromJson(await fetch("/api/face/session", { method: "POST" }).then((r) => r.json()))}
  strings={TH}
  onResult={(r) => fetch("/api/face/done", { method: "POST", body: JSON.stringify({ sessionId: r.sessionId }) })}
/>
```

The device never sees the API key — `LumifaceClient` cannot even take one. Your backend holds it, creates the session with `POST /v1/sessions`, and reads the outcome with `GET /v1/sessions/{id}` once the app reports done. There is no backend SDK: it is two REST calls, and [`examples/backend`](examples/backend) is a complete one in Python.

The answer is the same from every client:

```json
{
  "ok": true,
  "mode": "verify",
  "reason_code": "OK",
  "scores": { "match": 0.71, "spoof": 0.93, "consistency": 0.88 },
  "verification_id": 42
}
```

`scores.match` is the lowest cosine similarity across the key frames against the enrolled face; it is `null` in liveness mode because there is nothing to match against.

## Enrol → verify

| Step | Who | What happens |
|---|---|---|
| **Enrol** | `POST /v1/subjects` with a photo, or `FaceFlow.enroll` from the camera | One frontal face, anti-spoof checked, stored as a 512-d ArcFace embedding under `external_id`. A second photo with `replace` updates it; `ttl_seconds` (or the policy's `subject_ttl_seconds`) drops it again after a while, a purge loop deletes the row. |
| **Session** | `POST /v1/sessions` from your backend with the API key | The server picks the challenges and flash colours, stamps a TTL, returns the client tunables and a `session_token` for the device. |
| **Challenge** | on the device | Blink / turn / nod / smile guided by ML Kit or MediaPipe, with the parallax check, then the flash; frames stream up the whole time (~8 fps) with an event at each boundary. |
| **Verify** | `WS /v1/sessions/{id}/stream` with the session token: frames flow up the whole time | The server clocks the flow itself, confirms each blink / smile / turn / nod from its own landmarks in the frames, reads the flash reflection, then anti-spoof → **match against `E001`** → consistency. The first failing check names the `reason_code`. |
| **Confirm** | `GET /v1/sessions/{id}` from your backend | Reads `result.ok`; the device's own report is not trusted. |

The live demo on the docs home runs `liveness` against a stand-in server because there is no enrolled subject in the browser; the example app and the React demo run all three flows against a real server.

## Examples

| | What it shows | Open |
|---|---|---|
| **Example backend** | The part of *your* system that holds the key: creates sessions, mints enrol tokens, reads the verdict. Both example apps talk to it | `bun run dev:backend` → http://localhost:8010 · [source](examples/backend) |
| **Flutter example** | Use cases (check-in, login, enrol, liveness), a subjects tab, history with scores, a preset picker; phone, Android emulator or Chrome | [source](examples/flutter) · [web](https://ga-mo.github.io/lumiface/docs/flutter/web) |
| **React demo** (Vite) | `LumifaceView` with themes and strings, the `useLumiface` hook and the headless controller | `bun run dev:react` → http://localhost:3010 · [source](examples/react) |
| **Docs site** | Guides, policy reference, reason codes, and a live demo of the real SDK with a stand-in server | `bun run dev:site` → http://localhost:3002 · [source](website) |

<p align="center">
  <img src="docs/images/flow.jpeg" width="820" alt="Three calls, one result: the device runs the challenges and the flash, the server runs MiniFASNet, the CVPR-2024 gate, the flash check and the ArcFace match">
</p>

## How it works

```
  device (Flutter / React)                          server (FastAPI)
  ────────────────────────                          ────────────────
  backend: POST /v1/sessions ───────────────────▶  pick 2 challenges (smile always) + 3 flash colours,
    ◀──────── session_token, client_config           TTL, project policy tunables
  WS /v1/sessions/{id}/stream  hello ───────────▶
    ◀──────── plan: challenges, colours
  ML Kit / MediaPipe guide the person
    blink · turn · nod · smile · flash ×3
  JPEG frames ~8 fps + boundary events ─────────▶  server clock   TIMING_*, FRAMES_STATIC
                                                    face          NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL
                                                    landmarks     blink / smile / turn / nod seen in the window
                                                                  → EXPRESSION_MISMATCH, POSE_MISMATCH
                                                    flash         chroma in each colour window → FLASH_FAIL
                                                    anti-spoof    MiniFASNet + CVPR-2024 gate  → SPOOF
                                                    identity      cosine(frame, enrolled) ≥ match_threshold → NO_MATCH
                                                    consistency   frames vs each other → INCONSISTENT
    ◀──────── {ok, reason_code, scores, verification_id}
```

Thresholds live in the policy (`match_threshold` 0.45 for `balanced`, 0.55 for `strict`, 0.40 for `relaxed`, ...); every one is listed with its default and meaning in the [policy reference](https://ga-mo.github.io/lumiface/docs/policy-reference). What the pipeline does not stop (latex and silicone masks past the smile, real-time deepfakes injected as a camera) is on the [security page](https://ga-mo.github.io/lumiface/docs/security). Lumiface is not certified liveness (no ISO 30107-3).

## Entry points

| | |
|---|---|
| `server/` | FastAPI: `app/routers` (subjects, sessions, verifications, policy, projects), `app/services` (face, antispoof, flash, expression, verify), `app/policy.py` (presets and schema) |
| `packages/lumiface/` | Flutter: `FaceVerifyView`, `FaceVerifyController`, `LumifaceClient`, `LivenessStrings`, `FaceVerifyTheme`; `android/` only carries the ProGuard keep rules ML Kit needs |
| `packages/lumiface-react/` | React: `LumifaceView`, `useLumiface`, headless controller, MediaPipe source; `@lumiface/react/core` is browser-free |
| `website/` | Docs (fumadocs + React Router), builds to `pages-site/` for GitHub Pages |
| `examples/` | `flutter` (use cases, subjects, history), `react` (Vite demo), `backend` (the key holder, ~100 lines) |
| `docs/plans/face-check-in.md` | Plan, status and the Android emulator setup |

## Working on it

```bash
cd server && uv run pytest -q                              # server
cd packages/lumiface && flutter analyze && flutter test    # Flutter package
bun install && bun run typecheck && bun run test:react     # React SDK + website
bun run dev:backend                                   # examples/backend on :8010
cd examples/flutter && flutter run -d <device>        # or -d chrome; use --release on a phone, debug hides R8 issues
bun run check:docs                                    # every reason code, event and client code has a docs line
bun run build:pages                                        # static docs into pages-site/
```

`server/scripts/calibrate.py` prints score distributions for a folder of real and attack captures; `eval_videos.py` runs the pipeline over attack videos; `eval_lfw.py` scores the matcher on LFW (99.52% 10-fold, EER 0.83%, no impostor pair above cosine 0.23; see [calibration](https://ga-mo.github.io/lumiface/docs/server/calibration)). Android emulator with the Mac webcam: AVD `face_test`, server at `http://10.0.2.2:8000`, preset `emulator`.
