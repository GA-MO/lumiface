# Face Check-in (Flutter + self-hosted verify/liveness server)

## Context

ต้องการ feature check-in ด้วยใบหน้า: พนักงานมีรูป register อยู่แล้ว ระบบต้องยืนยันว่าเป็นคนเดียวกัน และกันการเอารูปถ่าย/วิดีโอมาแอบอ้าง check-in แทนกัน ใช้ภายในทีม (non-commercial) ยังไม่มี backend จึงต้องเขียนใหม่ และอยากให้ reuse ได้กับหลาย project

ผล research (สรุปไว้ในแชทแล้ว): ไม่มี open-source liveness ตัวไหนถึงระดับ certified ผู้ใช้รับได้ เลือกแนวทาง **B – Hybrid**: client ทำ active liveness (challenge สุ่ม + จับเวลา) และเก็บ frame หลายภาพ, server ทำ passive anti-spoof + face verify + ตรวจความสอดคล้องข้าม frame เพราะ non-commercial จึงใช้ **InsightFace buffalo_l** (แม่นสุดในกลุ่มฟรี, LFW 99.83) ได้

เป้าหมายปลายทาง: iOS/Android เป็นหลัก, Web เป็น phase ท้าย (stack แยกเพราะ ML Kit ไม่รองรับ web)

## Stack ที่เลือก

| ส่วน | เลือก | เหตุผล |
|---|---|---|
| Server | Python 3.12, FastAPI, `insightface` (buffalo_l) + `onnxruntime`, MiniFASNet weights จาก minivision Silent-Face-Anti-Spoofing (Apache-2), SQLModel + SQLite (สลับ Postgres ได้ด้วย env), Docker | ทีมเดียวใช้ในหลาย project → API key ต่อ project, เบา, รันบน CPU ได้ |
| Flutter core | package `face_checkin` (reusable) + `example/` app | ใช้ซ้ำหลาย project โดย import package เดียว |
| Mobile ML | `camera`, `google_mlkit_face_detection` (active challenge signals: eyeOpenProb, smile, Euler Y/X) | ฟรี, on-device, มีข้อมูลครบสำหรับ challenge |
| Web ML (phase 5) | MediaPipe `@mediapipe/tasks-vision` FaceLandmarker ผ่าน `dart:js_interop` + `package:web` | ตัวเดียวที่ maintained และรันบน Safari |
| HTTP/state | `dio`, `freezed`/`json_serializable` สำหรับ model, `flutter_riverpod` ใน example เท่านั้น (package core ไม่ผูก state lib) | package ต้องเบาเพื่อ reuse |

## โครงสร้าง repo (monorepo)

```
flutter-face-check-in/
  docs/plans/face-check-in.md      ← copy ของ plan นี้ (ใช้กับ /go, /handoff)
  .claude/ship.md                  ← gate / ports สำหรับ /ship
  server/
    app/{main.py, config.py, db.py, models.py, routers/{enroll,session,checkin,admin}.py,
         services/{face.py, antispoof.py, challenge.py, verify.py}}
    weights/  (download script → buffalo_l, MiniFASNetV2 + V1SE .onnx)
    tests/    (pytest + รูปตัวอย่าง real/print/replay ที่เราถ่ายเอง)
    Dockerfile, docker-compose.yml, pyproject.toml (uv)
  packages/face_checkin/
    lib/src/{api/, liveness/, camera/, ui/}, lib/face_checkin.dart
    example/   (Flutter app: หน้า enroll, หน้า check-in, ตั้งค่า server URL)
```

## Flow หลัก

**Enroll (admin):** upload รูปพนักงาน → server ตรวจว่ามี 1 หน้า, หน้าตรง (yaw/pitch < 20°), ขนาด ≥ 112px, anti-spoof ผ่าน → เก็บ embedding 512-d (normalize แล้ว) ผูกกับ `employee_id` + `project_id`

**Check-in:**
1. Client `POST /sessions` → server สุ่ม challenge 2 ข้อจาก {blink, turn_left, turn_right, smile, nod} + ลำดับ + `session_id` (หมดอายุ 60 วิ) – สุ่มที่ server เพื่อกัน client แก้
2. Client รัน challenge ด้วย ML Kit: จับ transition (เช่น eyeOpen 0.8→<0.2→>0.8 ภายใน 50-500 ms, yaw ผ่าน ±25°) และเก็บ **frame JPEG** 4 ภาพ: neutral ก่อนเริ่ม, ตอน challenge 1 สำเร็จ, ตอน challenge 2 สำเร็จ, neutral หลังจบ + timestamp
3. Client `POST /sessions/{id}/verify` (multipart: frames + timings + employee_id)
4. Server ตรวจตามลำดับ (fail เร็วสุดก่อน):
   - session ยังไม่หมดอายุ, จำนวน frame ครบ, timing สมเหตุสมผล (เร็วเกิน = replay/script)
   - ทุก frame: detect 1 หน้า, anti-spoof (MiniFASNet ensemble V2 + V1SE) → เฉลี่ย score ต้อง ≥ threshold และไม่มี frame ไหนต่ำกว่า hard floor
   - frame ของ turn challenge: pose จาก insightface ต้องหันไปทิศที่สั่งจริง (server ยืนยันซ้ำ ไม่เชื่อ client)
   - embedding ทุก frame vs enrolled: cosine ≥ `MATCH_THRESHOLD` (เริ่ม 0.45 แล้ว calibrate phase 3) และ embedding ข้าม frame ต้อง cosine ≥ 0.6 ต่อกัน (กันสลับคนกลางทาง)
   - ผ่านทั้งหมด → บันทึก check-in (เวลา, employee, score ทั้งหมด, เก็บ frame ไว้ audit ตาม config)
5. Response: `{ok, reason_code, scores{match, spoof, consistency}}` client แสดงผล

## Endpoints (server)

- `POST /v1/employees` (multipart photo) · `GET /v1/employees` · `DELETE /v1/employees/{id}` – header `X-API-Key` → project
- `POST /v1/sessions` → `{session_id, challenges[], expires_at}`
- `POST /v1/sessions/{id}/verify` (multipart frames[], JSON meta) → result
- `GET /v1/checkins?from&to` – สำหรับดูประวัติ
- `GET /health`
- `POST /v1/debug/score` (เปิดเฉพาะ `DEBUG=1`): ส่งรูปเดียว ได้ spoof score + embedding เพื่อใช้ calibrate

## Flutter package `face_checkin` – public API

```dart
FaceCheckin.configure(baseUrl:, apiKey:);
FaceCheckinScreen(employeeId:, onResult: (CheckinResult r) {...})  // widget สำเร็จรูป
// ชั้นล่างสำหรับ project ที่อยาก custom UI:
LivenessController (state machine: idle → challenge(i) → capturing → uploading → done/failed)
FaceSignalSource (abstract) ← MlKitSignalSource (mobile), MediaPipeSignalSource (web, phase 5)
CheckinApi (dio)
```

Challenge state machine ต้อง testable โดยไม่ต้องมีกล้อง: รับ stream ของ `FaceSignal{eyeOpenL, eyeOpenR, smile, yaw, pitch, faceBox, ts}` แล้ว emit event → เขียน unit test ด้วย signal จำลอง

## Phases

### Phase 0 – Scaffold
- สร้างโครง repo ตามด้านบน, `git init`, `.gitignore` (weights/, *.db, ios/Pods)
- `docs/plans/face-check-in.md` = plan นี้, `.claude/ship.md` (gate: `cd server && uv run pytest -q && cd ../packages/face_checkin && flutter test`, ports: 8000)
- `flutter create --template=package packages/face_checkin` + `flutter create packages/face_checkin/example --platforms=ios,android,web`
- เสร็จเมื่อ: `flutter test` ใน package ผ่าน (test ว่าง), `uv run uvicorn app.main:app` ตอบ `/health`

### Phase 1 – Server: verify + anti-spoof
- `weights/download.py`: ดึง buffalo_l (insightface auto-download) และ MiniFASNet .onnx (แปลงจาก .pth ของ minivision ด้วย script ใน repo, หรือใช้ onnx ที่ community แปลงไว้ – ตรวจ hash แล้ว pin)
- `services/face.py`: FaceAnalysis(buffalo_l, CPU) → detect, pose, embedding; `services/antispoof.py`: crop ตาม scale 2.7 และ 4.0, 80x80, softmax 3 class, ensemble
- `services/challenge.py`: สุ่ม + ตรวจ timing; `services/verify.py`: pipeline ตาม flow ข้อ 4
- SQLModel: `Project(api_key)`, `Employee(project_id, external_id, name, embedding: bytes)`, `Session`, `Checkin`
- Dockerfile (python:3.12-slim + build-essential สำหรับ insightface), compose พร้อม volume weights/db
- tests: ใช้รูปที่เราถ่ายเอง 3 ชุด (คนจริง / รูปพิมพ์ / จอมือถือ) → assert spoof score แยกได้, verify same/different person
- เสร็จเมื่อ: `uv run pytest` ผ่าน และ `curl` enroll → session → verify ด้วยรูปจริงได้ `ok:true`, ด้วยรูปจากจอได้ `ok:false reason=spoof`

### Phase 2 – Flutter package + example บน iOS
- `MlKitSignalSource`: camera stream → `InputImage` (nv21 Android / bgra8888 iOS) → FaceDetector (performanceMode fast, classification + tracking on) → `FaceSignal`
- `LivenessController` + unit tests ด้วย signal จำลอง (blink ปกติผ่าน, blink ค้าง >500ms ไม่ผ่าน, หันไม่ถึงมุมไม่ผ่าน, timeout)
- `FaceCheckinScreen`: preview + วงรี guide + ข้อความ challenge + progress; เก็บ frame ตอน event ด้วย `takePicture` หรือแปลงจาก stream (เลือกอันที่เร็วกว่าบน iOS จริง)
- `CheckinApi` + `example/` (หน้า settings url/key, enroll จาก gallery, check-in)
- iOS: `NSCameraUsageDescription`, min iOS 15.5, รันบนเครื่องจริง (ML Kit + กล้องไม่รันบน simulator)
- เสร็จเมื่อ: บน iPhone จริง check-in ตัวเองผ่าน, ยกรูปตัวเองบนจอ/กระดาษให้กล้อง → ไม่ผ่าน (challenge ไม่สำเร็จ หรือ server ตอบ spoof)

### Phase 3 – Android + calibration
- รัน example บน Android จริง, แก้ rotation/format ของ `InputImage`
- `server/scripts/calibrate.py`: รับโฟลเดอร์รูปสมาชิกทีม (จริง/ปลอม) → พิมพ์ distribution ของ match cosine และ spoof score → เลือก threshold ลง `.env`
- เสร็จเมื่อ: ทีม ≥ 3 คน check-in ผ่านทุกคน และ cross-check (คน A ใช้ employee_id ของ B) ไม่ผ่าน

### Phase 4 – Hardening (จำเป็นก่อนใช้จริง)
- ขั้น A (server) ทำแล้ว: TIMING_TOO_SLOW, CVPR-2024 ResNet50 gate บน face crop (ดู สถานะ)
- ขั้น B (client) ทำแล้ว: **motion parallax** ใน `TurnDetector` – เปิด `enableLandmarks` ML Kit, `FaceSignal.noseParallax` = (nose.x − eyeMid.x)/ระยะตา ต้องเปลี่ยนจาก baseline หน้าตรง ≥ `parallaxMinShift` (0.08) ตอน yaw ≥ 25° ถึงผ่าน; ถ้า server ไม่สุ่ม turn มา client ต่อ turn เสริม 1 อัน (`parallaxWhenNoTurn`, ไม่ส่ง frame/duration เพิ่ม server ไม่รู้) · กันได้: รูปพิมพ์/รูปนิ่งบนจอที่เอียงทั้งแผ่น · กันไม่ได้: วิดีโอคนจริงหันหัว (parallax จริง) – ยังพึ่ง CVPR gate · **screen-flash** ทำแล้ว (client+server): session มี `flash_colors` 3 สีสุ่ม + `flash_hold_ms`, แอปเต็มจอทีละสี lock exposure แล้วส่ง `flash_<i>` 3 เฟรม, server (`services/flash.py`) วัด hue เฉลี่ยบนแก้ม ตัด mean และ grey แล้ว cosine กับลำดับที่สั่ง + ต้องชนะทุก permutation · เริ่มแบบ shadow mode (`FLASH_ENFORCE=0` บันทึก `details.flash`) จนกว่าจะ calibrate `FLASH_MIN_RESPONSE` บนมือถือจริง · server บังคับมี smile ทุก session (`REQUIRED_CHALLENGE`) เพราะหน้ากาก latex/silicone ผ่าน passive gate ทั้งสอง และ server ตรวจยิ้มซ้ำเองจาก 68 landmark (`services/expression.py`: ปากกว้างขึ้น ≥8% หรือมุมปากยกขึ้น ≥0.04 เทียบ neutral_start ไม่งั้น `EXPRESSION_MISMATCH`, วัดจาก sample: ยิ้มจริง gain 1.14–1.16 lift 0.068–0.071, neutral-neutral gain 0.93–1.05 lift −0.04..0.03) · example ดันความสว่างจอสูงสุดตอน flash ผ่าน `onFlashChanged` + `screen_brightness` (dependency ใน example เท่านั้น)
- iOS: `arkit_plugin` face-mesh Z-variance เป็น score เสริม (iPhone ที่มี Face ID)
- ผู้ใช้ตัดออกแล้ว: device binding, geofence, audit ด้วยคน, vision LLM (แพง) – ห้ามเสนอซ้ำ

### Phase 5 – Web (ทำแล้ว 2026-09-18)
- `MediaPipeSignalSource`: โหลด tasks-vision + `face_landmarker.task` (self-host ใน `web/`), ดึง `<video>` ที่ `camera_web` สร้างผ่าน `package:web`, map blendshapes (`eyeBlinkLeft/Right`, `mouthSmile`) + head matrix → `FaceSignal` เดิม
- frame capture ผ่าน canvas → JPEG blob
- conditional import `signal_source_stub.dart` / `_mobile.dart` / `_web.dart`
- ตั้ง COOP/COEP header ใน dev server และ service worker cache model
- เสร็จเมื่อ: Chrome desktop + iOS Safari check-in ผ่านด้วย flow เดียวกับ mobile (Chrome ผ่านแล้ว, Safari ยังไม่ทดสอบ)

### Phase 6 – React SDK (ทำแล้ว 2026-09-18)
- `packages/lumiface-react`: port ของ controller/detectors เป็น TypeScript, `MediaPipeSource`, `LumifaceView` + `useLumiface` render props เหมือน Flutter builders, vitest port ของ Dart tests
- เสร็จเมื่อ: `bun run test:react` + `bun run typecheck` ผ่าน, demo `bun run dev:react` verify ได้กับ server เดียวกัน

## ความเสี่ยงที่รู้แล้ว
- `insightface` pip ต้อง compile (Cython) – ใน Docker ใส่ build-essential; บน mac arm64 ใช้ได้
- MiniFASNet ในสภาพจริงกัน replay จากจอได้บางส่วน (benchmark 2026 ปล่อยผ่านสูง) → active challenge + timing + cross-frame consistency คือชั้นหลัก, MiniFASNet เป็น score เสริม
- ML Kit `takePicture` ระหว่าง stream บน iOS อาจกระตุก → fallback แปลง frame จาก stream เป็น JPEG ด้วย `image` package
- buffalo_l license non-commercial → ใส่ NOTICE ใน README

## Verification (ภาพรวม)
1. `cd server && uv run pytest -q`
2. `docker compose up` → `curl /health`, enroll/verify ด้วย curl ตาม README
3. `cd packages/face_checkin && flutter test` (state machine)
4. iPhone จริง: ผ่าน/ไม่ผ่าน ตาม "เสร็จเมื่อ" ของ phase 2-3
5. Web (phase 5): Chrome + iOS Safari

### Phase 12 – โหมดไม่มี flash + หน้า protocol (ทำแล้ว 2026-09-19)
- **ทุกด่านคำนวณเสมอ**: rewrite `analyze_stream` (`services/stream.py`, `_Gates`) — ทุก gate รันต่อแม้ด่านก่อนตก, `reason_code` = ด่านแรกที่ตก *และนับ* (flash นับเฉพาะเมื่อ `flash_enforce`), `details.gates` = verdict ของทุก gate ตามลำดับ pipeline. `GET /verifications` จึงเห็น spoof/cvpr/match ของ session ที่ตก flash โดยไม่ต้อง replay ด้วย env. test: `test_flash_enforced_rejects_unlit_frames` + `test_still_face_is_judged_by_every_gate`
- **attack set +3**: `scripts/attack_sessions.py` เล่น stored genuine session ใส่ server สดแบบไม่มีหน้า (injection = ภาพ+event เดิม cadence เดิม; photo = frame aligned zoom เข้าช่วง challenge; static = ค้างนิ่ง) → เก็บใน `data/sessions/attack/` (13 sessions). `FLASH_ENFORCE=0 uv run python scripts/replay_sessions.py data/sessions/attack` พิมพ์บรรทัด gate ต่อ session (`gate_line`): injection ผ่านทุก passive+match ตกแค่ flash(shadow) → ยืนยัน video injection กันได้ด้วย flash เท่านั้น
- **หน้า `docs/protocol`**: ลำดับ message, `format` 4 แบบ, กติกาเวลา (นาฬิกาเดียว), flash (เต็มจอ+brightness+exposure lock), event 4 ตัว, close/error codes — link จาก api.mdx/concepts/flutter+react custom-ui; `details` reference อยู่ใน `reason-codes.mdx#the-details-object` link จาก api/server×3
- เสร็จเมื่อ (ผ่าน): `uv run pytest -q` 108 passed; `FLASH_ENFORCE=0 … replay_sessions.py data/sessions/attack` แสดง gate ทุกด่านต่อ session; `bun run check:docs` + `bun run build:site` ผ่านกับหน้า protocol ใน sidebar

## สถานะ (updated 2026-09-19, branch `aws-detectors`, Phase 12 uncommitted)
ทำแล้ว: **Phase 12** (ยังไม่ commit — 13 ไฟล์ M + 2 ไฟล์ ??) — (1) ทุก gate คำนวณเสมอ: rewrite `analyze_stream` ด้วยคลาส `_Gates` ใน `server/app/services/stream.py`, `reason_code` = ด่านแรกที่ตก*และนับ* (flash นับเฉพาะเมื่อ `flash_enforce`), `details.gates` = verdict ทุก gate; test ใน `server/tests/test_api.py` (`test_flash_enforced_rejects_unlit_frames`, `test_still_face_is_judged_by_every_gate`) · (2) `server/scripts/attack_sessions.py` เล่น stored genuine ใส่ server สด 3 แบบ (injection/photo/static) → เก็บใน `server/data/sessions/attack/` (ตอนนี้ 13, ไม่ใน git); `replay_sessions.py` เพิ่ม `gate_line` พิมพ์ verdict ทุกด่านต่อ session · (3) หน้า `website/content/docs/protocol.mdx` (อยู่ใน `meta.json` หลัง api) + section `#the-details-object` ใน `reason-codes.mdx`, link จาก api/concepts/flutter+react custom-ui/server×3
ค้าง: ยังไม่ commit (รอ `/ship`) — พิสูจน์แล้วในเซสชันนี้: `uv run pytest -q` 108 passed, `bun run check:docs` ผ่าน, `bun run build:site` ผ่าน (protocol อยู่ใน sidebar, เปิดดูในเบราว์เซอร์แล้ว) · Phase 12 เดิมที่ยังค้าง: โหมดปิด flash (`flash_count:0`) เป็น accessibility path ยังไม่ทดสอบกับ attack **จริงหน้ากล้อง** 3 ชนิด (รูปพิมพ์/จอ monitor/video บนจอมือถือ) — ต้องมีคน · ค้างเดิม: threshold ทุกตัวจากคนเดียว, Chrome/Safari บนมือถือกับ video ยังไม่รัน, per-detector box scale (Vision 1.23×/BlazeFace 1.14× ของ insightface), `MODEL_URL` React ชี้ jsDelivr `gh/GA-MO/lumiface@main` ใช้ได้หลัง merge main
ค้นพบ: canvas injection (`attack_sessions.py --kind injection`) **ผ่าน passive gate + match หมด ตกแค่ flash** → ยืนยันว่า flash เป็นด่านเดียวที่กัน video injection; passive-only กันจอมือถือได้แต่ margin บาง · AWS Face Liveness มี flow แบบเดียวกันเป๊ะ (`FaceMovementAndLightChallenge` = face_move+flash, `FaceMovementChallenge` = oval อย่างเดียว) และไม่มีโหมด "ไม่มี flow" — เหตุผลเดียวกับเรา (`docs/research/aws-face-liveness.md`)
ถัดไป: /go ตรวจ โหมดปิด flash กับ attack จริงหน้ากล้อง 3 ชนิด ตาม docs/plans/face-check-in.md

### สถานะก่อนหน้า (2026-09-18 23:40)
ทำแล้ว (uncommitted ~45 ไฟล์): **Phase 9 — challenge แบบ AWS Face Liveness** ครบทั้ง server/2 SDK/docs: challenge `face_move` (plan ส่ง `oval`; server `movement_observed` ใน `stream.py`: growth ≥ `move_min_growth` 1.25, fill ≥ `move_min_fill` 0.85 ของวงรี, centred → `MOVEMENT_MISMATCH`; window ยาวได้ถึง `move_max_ms` 10 s) เป็น default ของ `balanced`; preset `gestures` = flow เดิม, `strict` = face_move + smile · SDK: `FaceMoveDetector` (เริ่มต้องแคบกว่า `move_start_max_ratio` 0.6 ของวงรี → hint tooClose "ถอยออก", เต็มเมื่อกว้าง ≥ `oval_min_fill` 0.85 และกึ่งกลางเบี่ยง ≤20% ของวงรี, ค้าง `oval_hold_ms` 500), `LivenessState.target`, FaceGuide วาดวงรีของ server, `frameAspect` จาก view; `AlignHint` ย้ายไป models.dart · หน้า docs ใหม่ `compare-aws.mdx` + ทุกหน้าที่เอ่ยท่าทาง, README, home, flow-animation · **รันสดบน Chrome (React :3010) แล้ว**: OK 2 รอบ (#68 growth 1.32 fill 0.90; #70 growth 1.37 fill 0.93, flash 20–24, match 0.75–0.81) หลังแก้ 3 รอบ: หน่วยวงรี → ด้านสั้นของเฟรม (เดิม 0.62 ของความกว้างทำวงรีสูง 112% บน webcam แนวนอน), IoU 0.7 → fill+centre (หน้าอยู่ต่ำกว่าวงรี 0.12–0.20 บน Mac เพราะกล้องอยู่เหนือจอ IoU ไม่เคยถึง), `max_challenge_ms` 5 s สั้นไปสำหรับเดินเข้าวงรี · session ทั้งหมดเก็บใน `server/data/frames/1/` (19 session)
ค้าง: (1) **ยังไม่ได้พิสูจน์ค่า 0.6 ล่าสุด**: 3 รอบก่อนหน้า (#71–73) client รับแต่ server เห็น growth 1.08–1.13 เพราะคนเริ่มใกล้ (0.50 ของด้านสั้น) — เปลี่ยน start เป็น 0.6 แล้วยังไม่มีใครลอง; ต้อง Chrome 3 รอบ + วิดีโอ 2 รอบ แล้ว S25+/iPhone (build ใหม่ทั้งคู่) เปิด `STORE_FRAMES=1 DEBUG=1` และดู `details.challenge_0` (2) จัด session face_move เข้า `data/sessions/genuine|attack` (ตอนนี้ set มีแค่ท่าเดิม 7) (3) ยังไม่ได้พิสูจน์หลังแก้รอบสุดท้าย: `cd server && uv run pytest -q` เต็มชุด (รันไปก่อนเปลี่ยน 0.6), `bun run check:docs`, `cd website && bun run build` (policy-reference ต้อง regenerate ให้มี `oval_min_fill`/`move_max_ms`) (4) เดิม: คนอื่น ≥3, CPU iOS, server สาธารณะ
ค้นพบ: กล่องหน้าของแต่ละ detector ไม่เท่ากัน (MediaPipe เล็กกว่า insightface ~20% ที่ระยะไกล, เท่ากันที่ระยะใกล้) → ห้ามเทียบ threshold client/server ข้ามหน่วย ต้องตั้งแยกและวัดจริง; AWS ก็ไม่เทียบ (client BlazeFace/Vision ตัดสิน "เข้าวงรี", Rekognition ตัดสินจากวิดีโอเอง) · AWS ไม่ใช้ lib เดียวกับเรา (BlazeFace web/Android, Apple Vision iOS) · ผู้ใช้บนเว็บอยู่ที่ ~0.5 ของด้านสั้นอยู่แล้วตอน align → ต้องบังคับ "ถอยออก" ก่อน ไม่งั้นไม่มี growth · Vite ส่งต่อแค่ console.warn/error ไม่ใช่ log; chrome-devtools MCP ไม่ได้ต่อกับ Chrome ของผู้ใช้ · ตัด smile ออกจาก default = ไม่มีด่านหน้ากากใน balanced (AWS ก็ไม่มี) บันทึกใน security.mdx
ถัดไป: /go ตรวจ face_move หลังค่า start 0.6 บน Chrome/S25+/iPhone แล้วจัด dataset ตาม docs/plans/face-check-in.md

### สถานะก่อนหน้า (2026-09-18 22:00)
ทำแล้ว: Phase 0–8 commit แล้วทั้งหมด (ล่าสุด a2bdffe) — stream WS + server ตัดสินเอง, device tokens, REST-only backend, examples/, docs site · **Phase 8 พิสูจน์บนเครื่องจริง**: Galaxy S25+ release (คนจริง 13/15, replay 0/11), iPhone 12 Safari ทั้ง 2 SDK (8/9, replay 0/5), iPhone 12 native ML Kit (3/3, replay 0/4) · บั๊กที่เจอเฉพาะเครื่องจริงแก้แล้ว: R8 keep rules ใน package (Android plugin เปล่า), JPEG subsample 640 + encode ทีละเฟรม, server จัดเฟรมด้วย client ms (`placement_windows`), `challenge_done` หลัง settle, blink ส่งเฟรมตาปิดทันที + encode เฟรมที่ signal มาจาก + closed_ratio 0.75 + copy "หลับตาแล้วลืมตา", iOS: yawSign กลับทิศ/ไม่หมุนซ้ำ/un-mirror · docs อ่านเต็มเทียบ code แก้ 14 จุด, `bun run check:docs` + `tests/test_replay.py` อยู่ใน ship gate · replay harness: `STORE_FRAMES=1` เก็บ `session.json`, `scripts/replay_sessions.py`, ชุด `server/data/sessions/{genuine 3, attack 4}` (ไม่เข้า git)
ค้าง: (1) threshold ทุกตัว (flash locality 0.8, smile 1.08, blink 0.75, spoof floor 0.30) ยังมาจากคนเดียว — ต้องคนอื่น ≥3 + มือถือรุ่นกลาง เปิด `STORE_FRAMES=1 DEBUG=1` ทุกรอบแล้วจัดเข้า `data/sessions/` (2) CPU บน iOS ยังไม่วัด (Android ~195% ของ 800%) (3) fps มือถือ 6.3–7.7 ไม่ถึง 8 เพราะ encode Dart ~150 ms (4) server สาธารณะสำหรับ demo :3002 (ตอนนี้ stand-in ตัดสินอะไรไม่ได้ copy บอกไว้แล้ว; แนะนำ Hetzner SG/Fly sin + backend ถือ key + rate-limit) (5) `server/data/frames/1/` 60 MB เฟรมหน้าผู้ใช้จาก diagnose ลบได้ (6) Local: team Apple ใน `examples/flutter/ios/Flutter/Local.xcconfig` (git-ignored), ติดตั้ง iPhone ด้วย `devicectl` เพราะ launcher Flutter ล้ม
ค้นพบ: ML Kit iOS pods ไม่มี arm64-simulator → Simulator/RocketSim/SimCam ใช้ไม่ได้ ต้องเครื่องจริง+Apple ID · camera_avfoundation ส่งเฟรมกล้องหน้า iOS ตั้งตรง+กลับด้าน (Android ส่ง sensor orientation ไม่กลับด้าน) — เฟรมตะแคงทำ MiniFASNet 0.2–0.5 และ match 0.17 ทั้งที่โมเดลไม่ผิด: orientation สำคัญกว่า threshold · Xcode 26 ปฏิเสธ pod deployment target <15 (Podfile pin 15.5) · Vite 6+ ตอบ preflight เอง (cors:true ใน TLS mode) · debug build ซ่อนปัญหา R8 ต้องทดสอบ release · จอมือถือสะท้อน flash: locality (ring/face ≤0.8) คือด่านที่แยก replay ไม่ใช่ correlation · web demo :3002 ใช้ SDK จริงแต่ stand-in server จึงผ่านทุกอย่างโดยออกแบบ · `~/.pub-cache` และ gradle transforms หายกลางทาง (น่าจะโปรแกรมล้างพื้นที่) กู้ด้วย pub get / ลบ transforms · ตัดสินใจไม่แทน ML Kit ด้วย MediaPipe native (ทบทวนเมื่อ Flutter บังคับ SPM หรือ calibrate พบ web/app ต้องใช้ threshold คนละชุด); AWS ใช้ BlazeFace/Vision + server-driven — ทางนั้นต้องเปลี่ยนแนว challenge ไม่ใช่แค่สลับ plugin · ผู้ใช้ไม่ต้องการรอบสดซ้ำ: แก้ server ต้องผ่าน replay ก่อน (CLAUDE.md)
ถัดไป: /go ตรวจ threshold กับคนอื่น ≥3 และมือถือรุ่นกลางผ่าน replay set ตาม docs/plans/face-check-in.md

### บันทึกเก่า (2026-09-17, Phase 4)
emulator: `FLASH_ENFORCE=0` เพราะ "จอ" คือหน้าต่างบน Mac · ไฟล์ที่ adb push เข้า Android/data อ่านไม่ได้ ต้อง `run-as <pkg> cp` · MiniFASNet input BGR 0-255 · CVPR ต้อง face crop margin 0.3 (0.2 ปฏิเสธคนจริง, ≥0.4 ปล่อย replay) · insightface yaw>0 = หันขวา · latex/silicone mask ผ่าน passive ทั้งคู่ กันได้ด้วย smile server-check เท่านั้น · weights/cvpr2024/resnet50.onnx 94 MB ไม่เข้า git (`weights/convert_cvpr.py`) · tests/fixtures มีหน้าผู้ใช้ 9 ภาพ อาจย้ายออกจาก git
