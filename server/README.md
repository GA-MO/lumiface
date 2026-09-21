# Lumiface Server

Self-hosted face verification (1:1) + passive liveness for the `lumiface` Flutter package and the `@lumiface/react` SDK. Multi-tenant: every project has an API key and a policy (preset + overrides) changed through `PUT /v1/policy`; the session carries the client tunables. Full docs in `website/content/docs/server`.

- Detection / pose / embedding: InsightFace **buffalo_l** (ArcFace r50). *Non-commercial licence on the weights.*
- Video from the devices (`services/video.py`): PyAV decodes WebM/VP8, MP4/H.264 and raw H.264 access units into JPEG frames with both clocks before the pipeline runs; a JPEG-per-message client is still accepted (`format: jpeg`).
- Passive anti-spoof, two gates: **MiniFASNet V2 + V1SE** ensemble (Apache-2.0, ONNX committed in `weights/`) and the
  **CVPR-2024 FAS challenge ResNet50** (MIT) on a face crop, which catches phone-screen replay even when no bezel is
  visible. The 94 MB ResNet ONNX is not in git: `uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py`.
- Active liveness is guided by the client and judged here: the server clocks the
  session, reads the face's move into the oval (`face_move`, the only challenge: box growth and fit,
  `services/stream.py: movement_observed`) from its own detector inside the window the device's events mark, and
  requires the same identity across the key frames and the flash frames. There is no gesture challenge: the device only sees a face box
  (BlazeFace on the web and Android, Apple Vision on iOS), so a rigid mask is left to the passive gates.
- **Screen-flash** (`services/flash.py`): the plan carries 3 random saturated colours; the app fills the
  screen with each one for `flash_hold_ms` while frames keep streaming. The server averages the cheeks over each
  colour's window and compares the hue shifts with the commanded sequence (order must beat every other permutation). A phone screen replaying a video emits
  its own light and reflects almost nothing; a recording cannot know colours chosen seconds earlier.
  A glossy phone screen *does* reflect the flash (Galaxy S25+ replay: correlation 0.77-0.83), so the decisive
  test is locality: the ring around the face must reflect at most 0.8x what the face does (real face 0.47-0.52
  because the wall is further away; phone screen 1.15-2.31 because the whole sheet reflects; with the oval flow on
  2026-09-19: real faces 0.02-0.56 across a MacBook, a Galaxy S25+ and an iPhone 12, phone-screen replays 1.5-8.6). Enforced by
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

The project key (`lf_sk_…`) belongs on your backend; the server stores only its SHA-256 (`project.api_key_hash`) and
shows it once, at creation or rotation (a database from before hashes its keys and drops the plaintext column on
first start). A device gets the `session_token` returned by `POST /v1/sessions`
(that session only) and sends it in the stream's hello. Session tokens die with the session.
A key sent from a browser page other than localhost is refused (401 `API_KEY_FROM_BROWSER`)
unless the project's policy sets `allow_browser_api_key`.
The backend then reads the outcome with `GET /v1/sessions/{id}` rather than trusting the device's report.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/projects` | json `{name, preset?}` | admin; returns the api key once |
| GET | `/v1/projects` | | admin |
| POST | `/v1/projects/{id}/rotate-key` | | admin |
| DELETE | `/v1/projects/{id}` | | admin |
| GET/PUT/DELETE | `/v1/policy` | `{preset?, overrides?, merge?}` | project policy; `/presets`, `/schema` |
| POST | `/v1/sessions` | json `{reference_photo?, purpose?}` | `reference_photo` (base64; one frontal face or 422 with a `reason_code`; not anti-spoof checked; never stored: its embedding is dropped when the stream claims the session) = verify against that photo; omitted = liveness only. Returns `session_token`, `client_config` — not the plan |
| WS | `/v1/sessions/{id}/stream` | `{"type":"hello","token","format"}` → plan; binary chunks (8-byte device ms + video chunk or JPEG) + events → `{"type":"end"}` → result | single use, spent on hello; the server clocks and judges everything itself |
| GET | `/v1/sessions/{id}` | | backend reads `{used, result}` after the device is done |
| GET | `/v1/verifications?from&to&session_id&purpose&ok` | | history; `reference` true = verify |
| POST | `/v1/debug/score` | multipart `photo` | only with `DEBUG=1` |

The stream, from the device's side (`app/routers/sessions.py` has the exact messages):

```
hello {token, format}  ▶   webm | mp4 | h264 | jpeg
              ◀ plan {challenges, flash_colors, flash_hold_ms, client_config}
chunks         ▶  as the recorder cuts them: 8-byte big-endian device ms + video chunk (or one JPEG)
event aligned / challenge_done i / flash i / flash_end  ▶  as the device reaches each boundary
end            ▶
              ◀ result {ok, mode, reason_code, scores, verification_id}
```

The server stamps frames and events with its own clock and, inside the challenge window, runs its own detector:
face_move = the box grew from far (`move_min_growth`) into the oval (`move_min_fill`) and ended centred; the flash
reflection is read from the frames of each colour window; anti-spoof, identity and
consistency run on the key frames it picked, identity also on the middle frame of each flash window (`app/services/stream.py`). Durations are measured on the server clock; the device's own stamps (frame header, event `ts`) only decide which window a frame belongs to, because a phone uploads a frame a few hundred ms after it was taken while its events arrive at once.

Verify response: `{ok, mode, reason_code, scores:{match, spoof, consistency}, verification_id}`.
Reason codes: `OK, FRAME_COUNT, FRAMES_STATIC, TIMING_ORDER, TIMING_TOO_FAST, TIMING_TOO_SLOW,
NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL, SPOOF, MOVEMENT_MISMATCH, FLASH_FAIL, NO_MATCH, INCONSISTENT`
plus stream-level `SESSION_NOT_FOUND, SESSION_USED, SESSION_EXPIRED, HELLO_INVALID, EVENT_INVALID, PAYLOAD_TOO_LARGE, SERVER_BUSY`
(the worker holds `MAX_OPEN_STREAMS` sockets; sent before the hello, the session stays unspent)
and auth-level `API_KEY_MISSING, API_KEY_INVALID, API_KEY_FROM_BROWSER, TOKEN_INVALID, ADMIN_KEY_UNSET, ADMIN_KEY_INVALID`; a `reference_photo` answers `BAD_IMAGE` (does not decode), `NO_FACE`, `MULTIPLE_FACES`,
`FACE_TOO_SMALL` or `POSE_NOT_FRONTAL` at session creation (a streamed frame that does not decode is skipped). Streams are capped by `MAX_UPLOAD_BYTES` (32 MB), `MAX_FRAME_BYTES` (4 MB), `MAX_STREAM_FRAMES` (900) and `MAX_IMAGE_PIXELS` (20 Mpx).

## Capacity

The CPU work of a session (about 24 detector passes and five anti-spoof passes) happens at `end`; streaming only
buffers. `app/services/inference.py` runs every CPU step in one pool of `MAX_CONCURRENT_ANALYSES` threads (default
cores ÷ `INFERENCE_THREADS`, itself 2), each ONNX session pinned to `INFERENCE_THREADS` intra-op threads, and the
stream handler closes a new socket `SERVER_BUSY` once `MAX_OPEN_STREAMS` (default 4 × the pool) are open so the
queue stays short. `DET_SIZE` is 320: the SDKs send a 640 px long side, and the replay set judges the same at 320
as at 640 for half the detector cost. Measured 2026-09-20 on an Apple M4 (10 cores), eight stored genuine
sessions: unpinned ONNX threads 0.18 sessions/s sequential, 0.10–0.12 with 4–8 in flight; the pool as shipped (5 analyses × 2
threads, `DET_SIZE=320`), 1.17 sessions/s with 8 in flight. With `WORKERS` above 1 each process loads its own models (~1 GB)
and its own pool; keep `WORKERS × MAX_CONCURRENT_ANALYSES × INFERENCE_THREADS` at the core count and use Postgres.

## Policy

Environment variables (`MATCH_THRESHOLD`, `FLASH_ENFORCE`, ...) are the defaults of the `balanced` preset. A project resolves
**env → preset → overrides** per request (`app/policy.py`); services read `get_policy()`. Presets: `balanced`, `strict`,
`relaxed`, `emulator`. `GET /v1/policy/schema` lists every field with its description; the docs site generates
`policy-reference` from it.

## Retention

The server keeps no face between sessions: there is no subject store, and a session's `reference_photo` never reaches
disk — its embedding is cleared from the session row in the statement that marks the session used, or purged with the
session if it is never opened. A background loop (`app/services/retention.py`, every `RETENTION_INTERVAL_SECONDS`,
default 300; `0` disables) deletes sessions older than `SESSION_PURGE_GRACE_SECONDS` (default 3600). Verifications are
kept as the audit log (scores and `details`, no embedding). A database from before enrolment was removed has its
`subject` and `enroltoken` tables dropped on start and `verification` rebuilt without its `subject_id` column. `STORE_FRAMES=1` (development) writes each session's frames and
`reference.npy` to `FRAMES_DIR` for `scripts/replay_sessions.py`.

## Tests

`uv run pytest -q`. API tests run with `FLASH_ENFORCE=0` and `OVAL_WIDTH_FRACTION=0.35` because they stream stills:
a padded copy of the same still plays the far face, the still itself the near one; the enforced paths are covered
through `PUT /v1/policy` overrides.
