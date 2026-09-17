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

### Phase 4 – Hardening (เลือกทำ)
- Server: จำกัด attempt ต่อ employee/นาที, เก็บ frame ล้มเหลวไว้ตรวจ, log reason_code
- iOS: `smart_liveliness_detection` หรือ `arkit_plugin` ตรวจ face-mesh Z-variance เป็น signal เสริม (iPhone ที่มี Face ID) – ส่ง flag ไป server เป็น score เพิ่ม ไม่ใช่ gate
- Android: ตรวจ screen-flash reflection (เปลี่ยนสีจอแล้วดูค่าเฉลี่ยความสว่างหน้าเปลี่ยนตาม)

### Phase 5 – Web (bonus)
- `MediaPipeSignalSource`: โหลด tasks-vision + `face_landmarker.task` (self-host ใน `web/`), ดึง `<video>` ที่ `camera_web` สร้างผ่าน `package:web`, map blendshapes (`eyeBlinkLeft/Right`, `mouthSmile`) + head matrix → `FaceSignal` เดิม
- frame capture ผ่าน canvas → JPEG blob
- conditional import `signal_source_stub.dart` / `_mobile.dart` / `_web.dart`
- ตั้ง COOP/COEP header ใน dev server และ service worker cache model
- เสร็จเมื่อ: Chrome desktop + iOS Safari check-in ผ่านด้วย flow เดียวกับ mobile

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

## สถานะ (updated 2026-09-17)
ทำแล้ว: Phase 0–1 ครบ · Phase 2 พิสูจน์แล้วบน Android emulator + webcam ของ Mac (README มีวิธีตั้งค่า): check-in ผ่านจริง 2 ครั้ง (smile+turn_right: match 0.70/spoof 0.99/consistency 0.65, smile+blink: match 0.68/spoof 0.99/consistency 0.75) กรอบหน้าจาก ML Kit ทาบตำแหน่งถูก · แก้บั๊ก Theme.of ใน initState · เพิ่ม: frame สุดท้ายต้องหันหน้าตรงก่อนถ่าย (กัน consistency ตก) · server strict direction ใช้ insightface yaw>0 = หันขวา (จากข้อมูลจริง) · 19 pytest + 16 flutter test ผ่าน
ทดสอบ spoof แล้ว (2026-09-17, รูปตัวเองบนจอมือถือยื่นให้ webcam): ล้มเหลวฝั่ง client 4/4 ครั้ง (blink→TIMEOUT, nod→TIMEOUT ×2, nod→FACE_LOST เพราะ ML Kit เห็น 2 หน้า คือรูป+คนถือ) ไม่มี frame ถึง server · MiniFASNet บน screenshot ที่มีรูปในมือถือให้ real 0.14 และ 0.003 (< 0.5 → SPOOF) ขณะที่ match กับ enrolled ยัง 0.49–0.57 (เกิน 0.45) แปลว่าถ้า challenge หลุด ชั้น passive ยังกัน · จุดอ่อนที่เห็น: การเอียงรูปทำ pitch ได้ถึง −7° (nod ต้อง 15°) ยังไม่ทะลุ
ทดสอบวิดีโอแล้ว (วิดีโอตัวเองเล่นบนจอมือถือ 5 ครั้ง): **วิดีโอผ่าน active challenge ฝั่ง client ได้ทุกครั้ง** (blink/turn/nod) frame ถึง server ทุกครั้ง → server ปฏิเสธทั้ง 5: MULTIPLE_FACES ×2 (เห็นคนถือ) และ SPOOF ×3 โดย MiniFASNet ให้ real = 0.0 ทุก frame ที่เป็นจอมือถือ (ครั้งที่ frame แรกเป็นหน้าจริงได้ 0.87–0.94 แล้ว mean 0.45 ยังต่ำกว่า 0.5 + hard floor 0.3 ตัดทิ้ง) · เก็บ frame เป็น tests/fixtures (replay_phone_*, real_webcam_*) + test_antispoof_fixtures.py · สรุป: ชั้น passive คือด่านหลักสำหรับวิดีโอ ส่วน active กันได้แค่รูปนิ่ง
**ค้นพบสำคัญ (2026-09-17 ค่ำ):** เมื่อ crop ขอบมือถือออกจาก frame วิดีโอที่เก็บไว้ (inner 50–70%) MiniFASNet ให้ real 0.7–0.95 → การปฏิเสธก่อนหน้ามาจาก 'เห็นขอบจอ' ไม่ใช่ texture ของจอ · frame ที่อัปโหลดมีแค่ 480×640 (ResolutionPreset.medium) น่าจะทำลาย moiré · เปลี่ยน default เป็น ResolutionPreset.high แล้ว รอทดสอบซ้ำแบบยกมือถือชิดกล้อง
ทดสอบวิดีโอชิดกล้อง (ไม่เห็นขอบ, ResolutionPreset.high, frame 720×1280) แล้ว = check-in #10: **anti-spoof ผ่าน** (mean 0.71; frames 0.74/0.33/0.97/0.79) และ match ผ่าน (0.49 > 0.45) ถูกปฏิเสธด้วย INCONSISTENT (0.41) เพียงเพราะ frame หันซ้ายเป็น profile −72° · คือวิดีโอเกือบทะลุทุกชั้น · เก็บเป็น tests/fixtures/replay_phone_close_* + test xfail(strict)
Phase 4 ขั้น A ทำแล้ว (2026-09-17 ค่ำ): (1) TIMING_TOO_SLOW: challenge ต้องสำเร็จภายใน MAX_CHALLENGE_MS=5000 และเก็บ durations/frame ts ลง details (2) ยก MATCH_THRESHOLD **ไม่ช่วย**: วิดีโอคนเดียวกันบนจอได้ match 0.63–0.80 เท่าหน้าจริง (3) **เพิ่ม gate ที่ 2: CVPR-2024 FAS ResNet50 (MIT) บน face crop +20% margin** → replay ไม่เห็นขอบได้ live ≤0.03 หน้าจริง 0.54–1.0; ใช้ full frame จะโดนหลอกเหมือน MiniFASNet; session #10 ที่เคยเกือบหลุดตอนนี้ SPOOF (cvpr_mean 0.008) · CVPR_THRESHOLD 0.30 / CVPR_HARD_FLOOR 0.10 · onnx 94MB ไม่เข้า git ใช้ weights/convert_cvpr.py (gdown + torch, sha256 pin) · Dockerfile COPY เพิ่ม · pytest 30 ผ่าน · เก็บ samples ถาวรที่ server/data/samples/
วิดีโอต้นฉบับจากผู้ใช้ (IMG_9256.MOV, iPhone 1080×1920 HEVC 14.8s) → server/data/samples/video/ ดึง 30 frame: match 0.40–0.80 (median 0.73), MiniFASNet 0.49–1.0 · **CVPR gate ไวต่อ crop margin มาก**: margin 0.2 ปฏิเสธ frame จริง 7/30 (false reject) · margin 0.3 = จุดสมดุล (จริง ≥0.30, webcam ≥0.81, replay ทุก frame ≤0.015) · margin ≥0.4 ปล่อย replay ไม่เห็นขอบ 1 frame (0.42) · ตั้ง CVPR_CROP_MARGIN=0.3, HARD_FLOOR=0.05 · เพิ่ม fixture real_phone_video_* กัน false reject · pytest 32 ผ่าน
ค้าง: (1) ขั้น B ชั้นฟิสิกส์ฝั่งแอป (parallax หรือ screen-flash) ยังไม่ทำ ตอนนี้พึ่ง CVPR gate ที่วัดจากคนเดียว/มือถือเดียว/webcam เดียว ต้องทดสอบกับจออื่น (iPad, monitor) และคนอื่นก่อนไว้ใจ (2) MobileNet ตัวเล็ก (6MB) ก็แยกได้ (replay ≤0.165 vs live ≥0.466) เผื่อ server เล็ก
ค้นพบ: MiniFASNet รับ BGR 0-255 ไม่หาร 255 · AVD บน Mac เห็นกล้องแค่ตัวเดียว (CameraX เตือน front lens หาย) แอป fallback ไปกล้องที่มี · emulator crop webcam แนวนอนเป็นแนวตั้ง ต้องนั่งกลางกล้อง · port 8000 เคยถูกโปรเซสอื่นใช้
ถัดไป: /go phase 2 ตาม docs/plans/face-check-in.md (ทดสอบ spoof + iPhone จริง) แล้วต่อ phase 3 calibrate
