# Facegate Server

Self-hosted face verification (1:1) + passive liveness for the `facegate` Flutter package and the `@facegate/react` SDK. Multi-tenant: every project has an API key and a policy (preset + overrides) changed through `PUT /v1/policy`; the session carries the client tunables. Full docs in `website/content/docs/server`.

- Detection / pose / embedding: InsightFace **buffalo_l** (ArcFace r50). *Non-commercial licence on the weights.*
- Passive anti-spoof, two gates: **MiniFASNet V2 + V1SE** ensemble (Apache-2.0, ONNX committed in `weights/`) and the
  **CVPR-2024 FAS challenge ResNet50** (MIT) on a face crop, which catches phone-screen replay even when no bezel is
  visible. The 94 MB ResNet ONNX is not in git: `uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py`.
- Active liveness is done by the client; the server re-checks timings and head pose and requires
  the same identity across every uploaded frame. Every session includes a smile (`REQUIRED_CHALLENGE`):
  latex/silicone masks pass both passive gates on the AxonData samples, and a rigid mask cannot smile. The server
  re-checks the smile itself (`services/expression.py`): on the `challenge_<i>` frame the mouth must be ≥ 8% wider
  or its corners ≥ 0.04 inter-ocular higher than on `neutral_start` (68-point landmarks), else `EXPRESSION_MISMATCH`.
- **Screen-flash** (`services/flash.py`): the session carries 3 random saturated colours; the app fills the
  screen with each one and uploads a `flash_<i>` frame. The server compares the hue shift on the cheeks with
  the commanded sequence (order must beat every other permutation). A phone screen replaying a video emits
  its own light and reflects almost nothing; a recording cannot know colours chosen seconds earlier.
  A glossy phone screen *does* reflect the flash (Galaxy S25+ replay: correlation 0.77-0.83), so the decisive
  test is locality: the ring around the face must reflect at most 0.8x what the face does (real face 0.47-0.52
  because the wall is further away; phone screen 1.15-2.31 because the whole sheet reflects). Enforced by
  default; set `FLASH_ENFORCE=0` on the Android emulator, whose "screen" is a small window on the Mac.

## Run locally

```bash
cd server
uv sync
uv run python weights/download.py            # buffalo_l (~300MB) + MiniFASNet .pth (hash-pinned)
# ONNX files are committed; regenerate with: uv run --with torch --with onnx python weights/convert.py
cp .env.example .env                         # set BOOTSTRAP_API_KEY
uv run uvicorn app.main:app --reload --port 8000
```

Docker: `docker compose up --build` (buffalo_l is downloaded into a volume on first start).

## API (header `X-API-Key`; admin endpoints `X-Admin-Key`)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/projects` | json `{name, preset?}` | admin; returns the api key once |
| GET | `/v1/projects` | | admin |
| POST | `/v1/projects/{id}/rotate-key` | | admin |
| DELETE | `/v1/projects/{id}` | | admin |
| GET/PUT/DELETE | `/v1/policy` | `{preset?, overrides?, merge?}` | project policy; `/presets`, `/schema` |
| POST | `/v1/subjects` | multipart `external_id`, `name`, `photo`, `replace` | enrol; 422 with `reason_code` if rejected |
| GET | `/v1/subjects`, `/v1/subjects/{id}` | | |
| DELETE | `/v1/subjects/{external_id}` | | |
| POST | `/v1/sessions` | json `{subject_id?, purpose?}` | `subject_id` omitted = liveness only; returns challenges, `flash_colors`, `frame_kinds`, `client_config` |
| POST | `/v1/sessions/{id}/verify` | multipart `subject_id?`, `meta` (json), `frames[]` in `frame_kinds` order | single use |
| GET | `/v1/verifications?from&to&subject_id&purpose&ok` | | history |
| POST | `/v1/debug/score` | multipart `photo` | only with `DEBUG=1` |

`meta` for verify:

```json
{"frames":[{"kind":"neutral_start","ts_ms":0},{"kind":"challenge_0","ts_ms":900},
           {"kind":"challenge_1","ts_ms":2100},{"kind":"flash_0","ts_ms":2600},{"kind":"flash_1","ts_ms":3050},
           {"kind":"flash_2","ts_ms":3500},{"kind":"neutral_end","ts_ms":3700}],
 "challenge_durations_ms":[420,380],"client":{"platform":"ios"}}
```

Verify response: `{ok, mode, reason_code, scores:{match, spoof, consistency}, verification_id}`.
Reason codes: `OK, FRAME_COUNT, FRAME_KINDS, TIMING_ORDER, TIMING_TOO_FAST, TIMING_TOO_SLOW, TIMING_DURATIONS,
NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL, SPOOF, POSE_MISMATCH, EXPRESSION_MISMATCH, FLASH_FAIL, NO_MATCH, INCONSISTENT`
plus HTTP-level `SESSION_NOT_FOUND, SESSION_USED, SESSION_EXPIRED, SUBJECT_MISMATCH, SUBJECT_NOT_FOUND, META_INVALID`.

## Policy

Environment variables (`MATCH_THRESHOLD`, `FLASH_ENFORCE`, ...) are the defaults of the `balanced` preset. A project resolves
**env → preset → overrides** per request (`app/policy.py`); services read `get_policy()`. Presets: `balanced`, `strict`,
`relaxed`, `emulator`. `GET /v1/policy/schema` lists every field with its description; the docs site generates
`policy-reference` from it.

## Tests

`uv run pytest -q` (53). API tests run with `CHALLENGE_POOL=blink,smile`, `SMILE_ENFORCE=0`, `FLASH_ENFORCE=0` because they
upload the same still for every frame; the enforced paths are covered through `PUT /v1/policy` overrides.
