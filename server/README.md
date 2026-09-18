# Face Check-in Server

Self-hosted face verification (1:1) + passive liveness for the `face_checkin` Flutter package.

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

## API (header `X-API-Key`)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/employees` | multipart `external_id`, `name`, `photo`, `replace` | enrol; 422 with `reason_code` if photo rejected |
| GET | `/v1/employees` | | |
| DELETE | `/v1/employees/{external_id}` | | |
| POST | `/v1/sessions` | json `{employee_id?}` | returns `session_id`, random `challenges`, `flash_colors` (hex), `flash_hold_ms`, `frame_kinds`, TTL |
| POST | `/v1/sessions/{id}/verify` | multipart `employee_id`, `meta` (json), `frames[]` in `frame_kinds` order | single use |
| GET | `/v1/checkins?from&to&employee_id&ok` | | history |
| POST | `/v1/debug/score` | multipart `photo` | only with `DEBUG=1`; raw scores for calibration |

`meta` for verify:

```json
{"frames":[{"kind":"neutral_start","ts_ms":0},{"kind":"challenge_0","ts_ms":900},
           {"kind":"challenge_1","ts_ms":2100},{"kind":"flash_0","ts_ms":2600},{"kind":"flash_1","ts_ms":3050},
           {"kind":"flash_2","ts_ms":3500},{"kind":"neutral_end","ts_ms":3700}],
 "challenge_durations_ms":[420,380],"client":{"platform":"ios"}}
```

Verify response: `{ok, reason_code, scores:{match, spoof, consistency}, checkin_id}`.
Reason codes: `OK, FRAME_COUNT, FRAME_KINDS, TIMING_ORDER, TIMING_TOO_FAST, TIMING_TOO_SLOW, TIMING_DURATIONS,
NO_FACE, MULTIPLE_FACES, FACE_TOO_SMALL, SPOOF, POSE_MISMATCH, EXPRESSION_MISMATCH, FLASH_FAIL, NO_MATCH, INCONSISTENT`
plus HTTP-level
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
Smile re-check: `SMILE_ENFORCE` (1), `SMILE_MIN_WIDTH_GAIN` (1.08), `SMILE_MIN_LIFT` (0.04).
Screen-flash: `FLASH_COUNT` (3, 0 disables), `FLASH_ENFORCE` (1), `FLASH_MIN_CORRELATION` (0.5),
`FLASH_MIN_RESPONSE` (2.0, RMS hue change in 8-bit units), `FLASH_MAX_BACKGROUND_RATIO` (0.8), `FLASH_HOLD_MS` (450).
Consistency: `CONSISTENCY_THRESHOLD` (0.60 between frontal frames), `CONSISTENCY_POSE_THRESHOLD` (0.40 for frames
taken mid turn/nod), `POSE_FRAME_MAX_ANGLE` (20). Measured 2026-09-18 on a Galaxy S25+ (9 genuine, 2 replay):
genuine correlation 0.95-0.99 / response 11-19 / ratio 0.47-0.52; replay 0.77-0.83 / 6-11 / 1.15-2.31.

## Evaluate against public attack videos

`uv run python scripts/eval_videos.py data/samples/axondata` scores folders of videos/stills with the same two
passive gates as verify and prints pass rates per category. The AxonData sample set (Hugging Face
`AxonData/face-anti-spoofing-dataset`, CC BY-NC 4.0, internal testing only) gave on 2026-09-17: genuine 14/14 pass;
phone replay 0/12, cut-out photo 0/5 and 3D paper mask 0/5 pass; **latex mask 3/3 and silicone mask 2/3 pass**,
hence the mandatory smile.

## Tests

`uv run pytest -q` (uses InsightFace's bundled sample photo; no spoof fixtures yet - drop printed/screen photos
into `tests/fixtures/spoof/` and extend `test_api.py` once the team has captured some).
