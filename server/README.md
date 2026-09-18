# Lumiface Server

Self-hosted face verification (1:1) + passive liveness for the `lumiface` Flutter package and the `@lumiface/react` SDK. Multi-tenant: every project has an API key and a policy (preset + overrides) changed through `PUT /v1/policy`; the session carries the client tunables. Full docs in `website/content/docs/server`.

- Detection / pose / embedding: InsightFace **buffalo_l** (ArcFace r50). *Non-commercial licence on the weights.*
- Passive anti-spoof, two gates: **MiniFASNet V2 + V1SE** ensemble (Apache-2.0, ONNX committed in `weights/`) and the
  **CVPR-2024 FAS challenge ResNet50** (MIT) on a face crop, which catches phone-screen replay even when no bezel is
  visible. The 94 MB ResNet ONNX is not in git: `uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py`.
- Active liveness is guided by the client and judged here: the server clocks the session, reads each blink, smile,
  turn and nod from its own landmarks inside the window the device's events mark, and requires the same identity
  across the key frames. Every session includes a smile (`REQUIRED_CHALLENGE`):
  latex/silicone masks pass both passive gates on the AxonData samples, and a rigid mask cannot smile. The server
  checks the smile itself (`services/expression.py`): on the best frame of the smile window the mouth must be ≥ 8% wider
  or its corners ≥ 0.04 inter-ocular higher than on the neutral frames (68-point landmarks), else `EXPRESSION_MISMATCH`.
- **Screen-flash** (`services/flash.py`): the plan carries 3 random saturated colours; the app fills the
  screen with each one for `flash_hold_ms` while frames keep streaming. The server averages the cheeks over each
  colour's window and compares the hue shifts with the commanded sequence (order must beat every other permutation). A phone screen replaying a video emits
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

The project key (`lf_sk_…`) belongs on your backend. A device gets the `session_token` returned by `POST /v1/sessions`
(verify only, that session only) or an enrol token from `POST /v1/subjects/tokens` (one enrolment of a fixed subject)
and sends it as `Authorization: Bearer …`. Session tokens die with the session; enrol tokens after
`ENROL_TOKEN_TTL_SECONDS`. A key sent from a browser page other than localhost is refused (401 `API_KEY_FROM_BROWSER`)
unless the project's policy sets `allow_browser_api_key`.
The backend then reads the outcome with `GET /v1/sessions/{id}` rather than trusting the device's report.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/projects` | json `{name, preset?}` | admin; returns the api key once |
| GET | `/v1/projects` | | admin |
| POST | `/v1/projects/{id}/rotate-key` | | admin |
| DELETE | `/v1/projects/{id}` | | admin |
| GET/PUT/DELETE | `/v1/policy` | `{preset?, overrides?, merge?}` | project policy; `/presets`, `/schema` |
| POST | `/v1/subjects/tokens` | json `{external_id, name?, ttl_seconds?, token_ttl_seconds?}` | single-use enrol token for a device; cannot replace an existing face |
| POST | `/v1/subjects` | multipart `external_id`, `name`, `photo`, `replace`, `ttl_seconds?` — or `photo` only with `Authorization: Bearer <enrol token>` | enrol; 422 with `reason_code` if rejected; `ttl_seconds` omitted = policy `subject_ttl_seconds`, 0 = keep |
| GET | `/v1/subjects`, `/v1/subjects/{id}` | | |
| DELETE | `/v1/subjects/{external_id}` | | |
| POST | `/v1/sessions` | json `{subject_id?, purpose?}` | `subject_id` omitted = liveness only; returns `session_token`, `client_config` — not the plan |
| WS | `/v1/sessions/{id}/stream` | `{"type":"hello","token"}` → plan; binary frames (8-byte client ms + JPEG) + events → `{"type":"end"}` → result | single use, spent on hello; the server clocks and judges everything itself |
| GET | `/v1/sessions/{id}` | | backend reads `{used, result}` after the device is done |
| GET | `/v1/verifications?from&to&subject_id&session_id&purpose&ok` | | history |
| POST | `/v1/debug/score` | multipart `photo` | only with `DEBUG=1` |

The stream, from the device's side (`app/routers/sessions.py` has the exact messages):

```
hello {token}  ▶
              ◀ plan {challenges, flash_colors, flash_hold_ms, client_config}
frames         ▶  continuously, ~8 fps: 8-byte big-endian client ms + JPEG
event aligned / challenge_done i / flash i / flash_end  ▶  as the device reaches each boundary
end            ▶
              ◀ result {ok, mode, reason_code, scores, verification_id}
```

The server stamps frames and events with its own clock and, inside each window, runs its own detector and 68-point
landmarks: blink = eye-aspect-ratio dip and recovery, smile = mouth width / corner lift vs the neutral frames, turn /
nod = yaw / pitch; the flash reflection is read from the frames of each colour window; anti-spoof, identity and
consistency run on the key frames it picked (`app/services/stream.py`). Durations are measured on the server clock; the device's own stamps (frame header, event `ts`) only decide which window a frame belongs to, because a phone uploads a frame a few hundred ms after it was taken while its events arrive at once.

Verify response: `{ok, mode, reason_code, scores:{match, spoof, consistency}, verification_id}`.
Reason codes: `OK, FRAME_COUNT, FRAMES_STATIC, TIMING_ORDER, TIMING_TOO_FAST, TIMING_TOO_SLOW,
NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL, SPOOF, POSE_MISMATCH, EXPRESSION_MISMATCH, FLASH_FAIL, NO_MATCH, INCONSISTENT`
plus stream-level `SESSION_NOT_FOUND, SESSION_USED, SESSION_EXPIRED, SUBJECT_NOT_FOUND, HELLO_INVALID, EVENT_INVALID,
ENROL_TOKEN_INVALID, ENROL_TOKEN_MISMATCH, EXTERNAL_ID_REQUIRED, PAYLOAD_TOO_LARGE, API_KEY_FROM_BROWSER`; `BAD_IMAGE` is the enrolment
verdict for a photo that does not decode (a streamed frame that does not decode is skipped). Streams are capped by `MAX_UPLOAD_BYTES` (32 MB), `MAX_FRAME_BYTES` (4 MB), `MAX_STREAM_FRAMES` (900) and `MAX_IMAGE_PIXELS` (20 Mpx).

## Policy

Environment variables (`MATCH_THRESHOLD`, `FLASH_ENFORCE`, ...) are the defaults of the `balanced` preset. A project resolves
**env → preset → overrides** per request (`app/policy.py`); services read `get_policy()`. Presets: `balanced`, `strict`,
`relaxed`, `emulator`. `GET /v1/policy/schema` lists every field with its description; the docs site generates
`policy-reference` from it.

## Retention

Embeddings are biometric data, so every subject can carry an expiry. `subject_ttl_seconds` (env, preset or project
override) is the default for `POST /v1/subjects`; `ttl_seconds` on the request wins, `0` keeps the subject until
`DELETE`. An expired subject answers `SUBJECT_NOT_FOUND` at once and can be enrolled again without `replace`.
A background loop (`app/services/retention.py`, every `RETENTION_INTERVAL_SECONDS`, default 300; `0` disables) deletes
expired subjects and sessions older than `SESSION_PURGE_GRACE_SECONDS` (default 3600). Verifications are kept as the
audit log with their `subject_id` link cleared.

## Tests

`uv run pytest -q` (65). API tests run with `CHALLENGE_POOL=blink,smile`, `SMILE_ENFORCE=0`, `FLASH_ENFORCE=0` because they
upload the same still for every frame; the enforced paths are covered through `PUT /v1/policy` overrides.
