# Face Check-in Server

Self-hosted face verification (1:1) + passive liveness for the `face_checkin` Flutter package.

- Detection / pose / embedding: InsightFace **buffalo_l** (ArcFace r50). *Non-commercial licence on the weights.*
- Passive anti-spoof, two gates: **MiniFASNet V2 + V1SE** ensemble (Apache-2.0, ONNX committed in `weights/`) and the
  **CVPR-2024 FAS challenge ResNet50** (MIT) on a face crop, which catches phone-screen replay even when no bezel is
  visible. The 94 MB ResNet ONNX is not in git: `uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py`.
- Active liveness is done by the client; the server re-checks timings and head pose and requires
  the same identity across every uploaded frame.

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

## API (header `X-API-Key`)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/employees` | multipart `external_id`, `name`, `photo`, `replace` | enrol; 422 with `reason_code` if photo rejected |
| GET | `/v1/employees` | | |
| DELETE | `/v1/employees/{external_id}` | | |
| POST | `/v1/sessions` | json `{employee_id?}` | returns `session_id`, random `challenges`, `frame_kinds`, TTL |
| POST | `/v1/sessions/{id}/verify` | multipart `employee_id`, `meta` (json), `frames[]` in `frame_kinds` order | single use |
| GET | `/v1/checkins?from&to&employee_id&ok` | | history |
| POST | `/v1/debug/score` | multipart `photo` | only with `DEBUG=1`; raw scores for calibration |

`meta` for verify:

```json
{"frames":[{"kind":"neutral_start","ts_ms":0},{"kind":"challenge_0","ts_ms":900},
           {"kind":"challenge_1","ts_ms":2100},{"kind":"neutral_end","ts_ms":2600}],
 "challenge_durations_ms":[420,380],"client":{"platform":"ios"}}
```

Verify response: `{ok, reason_code, scores:{match, spoof, consistency}, checkin_id}`.
Reason codes: `OK, FRAME_COUNT, FRAME_KINDS, TIMING_ORDER, TIMING_TOO_FAST, TIMING_TOO_SLOW, TIMING_DURATIONS,
NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL, SPOOF, POSE_MISMATCH, NO_MATCH, INCONSISTENT` plus HTTP-level
`SESSION_USED (409), SESSION_EXPIRED (410), EMPLOYEE_NOT_FOUND (404), EMPLOYEE_MISMATCH (400)`.

## Curl walkthrough

```bash
K='X-API-Key: change-me'
curl -H "$K" -F external_id=E001 -F name=Alice -F photo=@alice.jpg localhost:8000/v1/employees
S=$(curl -s -H "$K" -H 'content-type: application/json' -d '{"employee_id":"E001"}' localhost:8000/v1/sessions)
echo $S   # note session_id + challenges
curl -H "$K" -F employee_id=E001 -F 'meta={"frames":[...],"challenge_durations_ms":[400,400]}' \
  -F frames=@f0.jpg -F frames=@f1.jpg -F frames=@f2.jpg -F frames=@f3.jpg \
  localhost:8000/v1/sessions/<session_id>/verify
```

## Thresholds (`.env`)

`MATCH_THRESHOLD` (0.45), `CONSISTENCY_THRESHOLD` (0.60), `SPOOF_THRESHOLD` (0.50), `SPOOF_HARD_FLOOR` (0.30),
`CVPR_CROP_MARGIN` (0.30), `CVPR_THRESHOLD` (0.30), `CVPR_HARD_FLOOR` (0.05), `MAX_CHALLENGE_MS` (5000),
`TURN_MIN_YAW` (20), `NOD_MIN_PITCH` (15), `MIN_SESSION_MS` (1500), `MIN_CHALLENGE_MS` (300).
Run `uv run python scripts/calibrate.py <photos-root>` with team photos to tune them.
`TURN_STRICT_DIRECTION=1` also enforces left/right sign once the camera mirroring convention is confirmed.

## Tests

`uv run pytest -q` (uses InsightFace's bundled sample photo; no spoof fixtures yet - drop printed/screen photos
into `tests/fixtures/spoof/` and extend `test_api.py` once the team has captured some).
