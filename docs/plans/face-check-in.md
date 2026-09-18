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

## สถานะ (updated 2026-09-18 evening)
ทำแล้ว: (2026-09-18 18:45, uncommitted) **Phase 8 บน Galaxy S25+ จริง (release APK, USB + adb reverse 8000/8010, server key `change-me` จาก .env)**: stream ผ่าน `web_socket_channel` ทำงานครบ · แก้ 4 บั๊กที่เจอเฉพาะมือถือจริง: (1) **R8 ทำ ML Kit พังใน release** (`InputImageConverterError` NPE ทุกเฟรม → "ไม่พบใบหน้า" จน TIMEOUT; debug build ไม่เจอ) → ทำให้ `lumiface` เป็น Android plugin เปล่า (`packages/lumiface/android/` + `consumer-rules.pro` keep `com.google.mlkit.**`, `gms.internal.mlkit_**`) Gradle merge ให้ทุกแอปเอง — พิสูจน์จาก R8 mapping ว่า `InputImage` ไม่ถูกย่อ และรันจริง OK โดยแอปไม่มี proguard ของตัวเอง (2) `captureJpeg` แปลง NV21 720p ทีละพิกเซล + spawn isolate ทุกเฟรมซ้อนกัน → CPU 550% → `image_convert.dart` subsample ด้านยาว ≤640 เขียน RGB ลง buffer ตรง + controller encode ทีละเฟรม (`_capturing`) → CPU เฉลี่ย 239% สูงสุด 307% (~2.4 คอร์/8) fps จริง 6.2–7.3 (3) **เฟรมมือถือถึง server ช้ากว่า event ~300 ms** (encode+ส่ง) → server จัดเฟรมสีแดงเข้าหน้าต่างสีถัดไป (FLASH_FAIL corr 0.27 ทั้งที่ response 25–35), blink ลืมตา/จุดหันสุดตกหน้าต่างถัดไป (POSE/EXPRESSION_MISMATCH) → `stream.py` `placement_windows` ใช้ client ms ในหัว 8 ไบต์ (มีอยู่แล้วแต่ไม่เคยใช้) จัดเฟรมเข้าหน้าต่าง ส่วนระยะเวลายังตัดสินด้วย server clock, client เก่าไม่ส่ง ts ใช้แบบเดิม (`details.placement`) (4) client ส่ง `challenge_done` ทันทีที่ตรวจเจอ → เฟรม "ลืมตาแล้ว" ตกนอกหน้าต่าง blink → ทั้ง 2 SDK ส่งเมื่อครบ settle 400 ms · **ผลหลังแก้: คนจริง 6/7 OK** (ตกครั้งเดียวก่อนแก้ข้อ 4) flash correlation 0.83–0.98 response 34–46 locality 0.38–0.45 match 0.69–0.80 cvpr 0.94–1.0 · **replay วิดีโอ loop จากมือถืออีกเครื่อง 8/8 กันได้**: TIMING_TOO_SLOW 3 (วิดีโอไม่ทำท่าตามสั่ง), EXPRESSION_MISMATCH 4 (smile gain 0.92–0.94, blink ไม่ลืมตา), FLASH_FAIL 1 (corr 0.89 แต่ locality **1.27** > 0.8 — กฎ locality คือด่านที่จับได้เมื่อ challenge บังเอิญตรง) · **React example :3010 กับ server จริง (webcam Mac)**: คนจริง OK (fps 7.7, flash resp 13.2, locality 0.28), replay วิดีโอ 4/4 กันได้ (FLASH_FAIL resp 2.5 locality 1.39, EXPRESSION_MISMATCH 2, TIMING_TOO_SLOW 1); S25+ replay อีก 3/3 กันได้ (TIMING 2, SPOOF minifasnet 1) · `flutter build ios --no-codesign` ผ่าน (ไม่มี iPhone ต่อ ยังไม่รันสด) · gate: pytest 65, flutter 41, vitest 27, typecheck 0
ค้าง: (1) /ship ชุดนี้ (2) keep rule กว้าง (`com.google.mlkit.**` ทั้งหมด) APK ใหญ่ขึ้นเล็กน้อย ถ้าอยากแคบต้องไล่จาก mapping ว่า class ไหนใน `mlkit_vision_common` ถูกตัด (3) fps มือถือ ~6.5 ไม่ถึง 8 เพราะ encode Dart ~150 ms/เฟรม ถ้าต้องการ 8 fps ต้อง encode native (YuvImage) หรือ ลด jpegQuality (4) iPhone จริงยังไม่รัน (5) เว็บ demo :3002 เป็น stand-in server — วิดีโอ loop ผ่านได้โดยออกแบบ; แก้ copy แล้ว (placeholder + ผลลัพธ์บอกว่า "Challenges done. The server's checks did not run here." ไม่ขึ้น OK เขียว) ถ้าจะโชว์กัน replay จริงต้อง host server สาธารณะ (แนะนำ Hetzner SG หรือ Fly `sin`, CPU-only 4 vCPU/4 GB + backend ถือ key + rate-limit + TTL สั้น)
ถัดไป: /ship → ทดสอบคนอื่น/มือถือรุ่นอื่น/iPhone

### สถานะก่อนหน้า (2026-09-18 evening)
ทำแล้ว: **Phase 7 device tokens** commit 669ab75 (session_token/enrol token, backend อ่านผลด้วย `GET /v1/sessions/{id}`, review 4 มุมแล้วแก้ครบ) · **Phase 8 (uncommitted, ~150 ไฟล์)**: (a) `LumifaceClient` ทั้ง 2 SDK รับแค่ URL — `LumifaceServerClient` ถูกลบ, backend ใช้ REST ตรง; server ปฏิเสธ key จาก browser Origin ที่ไม่ใช่ localhost (`API_KEY_FROM_BROWSER`, policy `allow_browser_api_key`), key ขึ้นต้น `lf_sk_` (b) ย้าย `packages/lumiface/example`→`examples/flutter`, `lumiface-react/demo`→`examples/react` (workspace, vite 8, stage 4:3 640×480, `/api`→:8010), เพิ่ม `examples/backend` (FastAPI ~100 บรรทัด ถือ key, `bun run dev:backend`) ทั้งสอง example คุยกับมันผ่าน HTTP (c) **stream แบบ AWS**: `WS /v1/sessions/{id}/stream` — hello{token}→plan (challenges/สีไม่อยู่ใน REST อีก)→JPEG ~8fps (8-byte BE ms + JPEG)+event aligned/challenge_done/flash/flash_end→end→result; `server/app/services/stream.py` ตัดสินจาก server clock + 68-landmark เอง (blink=EAR dip, smile, yaw/pitch, flash ใน window ของสี, FRAMES_STATIC); multipart `/verify`+`meta` ลบแล้ว; SDK ทั้ง 2 stream ผ่าน `VerifyStream` (d) alignment วัดใน `visibleRegion` ของ preview (เดิมวัดจากเฟรมดิบ→"Move closer" ตลอดบน webcam), guide ไม่ล้น/ไม่ทับ prompt, `VerifyResult.sessionId` ทุกกรณี, relaxed preset `min_face_width_fraction` 0.2 (e) docs/website ทั้งหมด incl. How-it-works animation 3 ฝ่าย · เทสสดผ่านทั้ง React (:3010) และ Flutter web (:3020) กับ server จริง: server เห็น blink EAR 0.26→0.17, smile gain 1.1, flash corr 0.78/0.95 · gate ล่าสุด: pytest 64, flutter 40, vitest 27, typecheck 0, site build ผ่าน (ก่อนแก้ home.tsx รอบสุดท้าย typecheck ผ่านแล้ว)
ค้าง: (1) ยัง**ไม่ commit** Phase 8 — `/ship` (2) ยังไม่ได้พิสูจน์ `cd website && bun run build` หลังแก้หัวข้อ "The device guides, the server decides" ใน `home.tsx` (typecheck ผ่าน) (3) flash บน React demo response 0.95 < min 2.0 เพราะ stage เล็ก — web จริงควร fullscreen ตอน flash หรือ preset relaxed (4) มือถือจริง (iOS/Android) ยังไม่รันหลัง stream: `web_socket_channel` + `setUint32` header, `captureJpeg` 8fps บน ML Kit path ยังไม่วัด CPU (5) blink บน server ใช้ทุกเฟรมใน window (≤48) — ถ้า fps ต่ำ/blink เร็วอาจพลาด, ไม่มี `blink_enforce` (บังคับเสมอ) (6) `STORE_FRAMES` เก็บทั้ง stream ไม่มี TTL (7) ข้อค้างเดิม: iPhone/Safari, คนอื่น/มือถืออื่น, ยังไม่ encrypt embedding at rest, verification log ไม่มี TTL, `flash_colors` ยังส่งให้ client (เหมือน AWS)
ค้นพบ: `ByteData.setUint64` ไม่มีบน dart2js → Flutter web ส่งเฟรมไม่ออกเงียบๆ (แก้เป็น 2×setUint32 แล้ว) · FastAPI parse multipart ก่อน dependency → auth-as-dependency กัน DoS ไม่ได้ ใช้ `BodyLimitMiddleware` แทน · `@vitejs/plugin-react@6` ต้อง vite 8 · PolicyScopeMiddleware ครอบเฉพาะ http; WS handler เรียก `use_policy` เองใน coroutine (to_thread copy contextvars ให้) · ผู้ใช้ยืนยันแนวทาง: ไม่มี SDK ฝั่ง key, demo/example ไม่อยู่ใน packages, backend ตัวอย่างเป็น Python แยก · Phase 4 ขั้น B (parallax client-side) ยังอยู่ แต่ blink/smile/turn/nod ตอนนี้ server ตัดสินเอง — ข้อความ "Who checks what" ใน concepts.mdx อัปเดตแล้ว
ถัดไป: /go ตรวจ Phase 8 บนมือถือจริง (iOS + Android: stream ผ่าน `web_socket_channel`, CPU ที่ 8 fps, flash response) ตาม docs/plans/face-check-in.md

### สถานะเดิม (2026-09-17)
ทำแล้ว: (2026-09-18 13:00) `scripts/eval_lfw.py` วัด matcher บน LFW 6,000 คู่: 10-fold 99.52% ± 0.34, EER 0.83% @0.147, impostor สูงสุด 0.23, FRR ต่อเฟรมที่ 0.40/0.45/0.55 = 1.9/3.2/10.7% FAR 0 ทุกค่า (27 รูปหาหน้าไม่เจอที่ 250px นับเป็น reject) → 0.45 ปลอดภัยฝั่ง FAR มาก ต้นทุนคือ FRR ที่ถูกคูณด้วย min 7 เฟรม ยังไม่ลด default รอ calibrate คนไทยจริง · (uncommitted 2026-09-18 02:10) ทดสอบสดบน Galaxy S25+ (SM-S936B, Android 16, ต่อ USB + adb reverse 8010): คนจริง 9 รอบ, replay จากมือถืออีกเครื่อง 2 รอบ → flash correlation คนจริง 0.95–0.99 response 11–19, replay 0.77–0.83 response 6–11 (**จอมือถือสะท้อน flash ได้** สมมติฐาน "จอไม่สะท้อน" ผิด) → เพิ่มกฎ locality: response รอบหน้า/บนหน้า ≤ 0.8 (จริง 0.47–0.52 ทั้ง 9, replay 1.15/2.31) แล้วเปิด `FLASH_ENFORCE=1` เป็นค่าเริ่มต้น · แก้บั๊ก 2 จุดจากการทดสอบ: neutral_end ถ่ายเร็วเกินหลัง flash (ยังติดสี MiniFASNet ตก 0.2) → `settleAfterFlashMs` 800; เฟรมพยักหน้า −40° consistency 0.47–0.55 → เกณฑ์ 0.40 สำหรับเฟรมเอียง >20° · emulator: คนจริง 3/3 ผ่าน, วิดีโอมือถือ 3/3 กันได้, รูปนิ่งเอียง 2/2 ค้าง TIMEOUT ฝั่งแอป (parallax) · pytest 47 ผ่าน · (2026-09-18 00:20) server ตรวจยิ้มซ้ำ + จอสว่างสุดตอน flash · (2026-09-17 22:05) screen-flash client+server, flutter test 24 ผ่าน, APK build ผ่าน (ยังไม่ได้รันสดเพราะไม่มีคนหน้ากล้อง) · ชุดทดสอบภายนอก AxonData (HF, CC BY-NC) 1.5GB ใน server/data/samples/axondata + `scripts/eval_videos.py`: genuine 14/14 ผ่าน, replay จอ/มือถือ 0/12, cut-out 0/5, paper mask 0/5 ผ่าน (กันได้หมด), **latex 3/3 silicone 2/3 ผ่าน** (กันไม่ได้ด้วย passive) · (uncommitted 2026-09-17 21:25) Phase 4 ขั้น B parallax: models/mlkit_camera_source/config/challenge_detector/liveness_controller + debug bar แสดง px= · flutter test 22 ผ่าน · วัดจริงด้วย ML Kit บน emulator จาก sample: หน้าจริงหัน 14°→26° Δpx=0.11, วิดีโอคนจริงหัน 0°→50° Δpx=0.59, รูปแบนบีบแนวนอน (ML Kit ยังรายงาน yaw −25) Δpx=0.026 → threshold 0.08 แยกได้ แต่ยังไม่ได้ลองคนจริงสดหน้ากล้อง · commit 4f019a6 = Phase 0–2 + Phase 3 ฝั่ง Android + Phase 4 ขั้น A · server: FastAPI + buffalo_l + 2 anti-spoof gate (MiniFASNet, CVPR-2024 ResNet50 face crop margin 0.3) + timing rules, pytest 32 ผ่าน · Flutter package `face_checkin` + example, flutter test 16 ผ่าน, iOS build ผ่าน · ทดสอบจริงบน Android emulator + webcam Mac (README มีวิธี): คนจริงผ่าน 3/3, รูปนิ่งกันได้ 4/4, วิดีโอบนจอกันได้ 6/6 หลังใส่ CVPR gate (ก่อนหน้า #10 เกือบหลุด) · ชุดข้อมูลถาวร server/data/samples/ (ไม่เข้า git) + fixtures ใน tests/fixtures (มีหน้าผู้ใช้ 9 ภาพ)
ค้าง: (0) flash เปิดบังคับแล้วจากข้อมูลคนเดียว/มือถือรุ่นเดียว/replay 2 รอบ ต้องยืนยันกับคนอื่น ≥2 และมือถือรุ่นอื่น (จอมืดกว่า S25+ response อาจต่ำ) และลอง replay บนจอด้าน/แท็บเล็ต/มอนิเตอร์ (ratio อาจต่างจากจอมือถือ) · MiniFASNet บน S25+ ให้คนจริงต่ำถึง 0.31 ในบางเฟรม (hard floor 0.30) เสี่ยง false reject ถ้าเจอบ่อยพิจารณาลด `SPOOF_HARD_FLOOR` เป็น 0.2 เพราะ CVPR+flash เป็นด่านหลักแล้ว · emulator ต้องตั้ง `FLASH_ENFORCE=0` · หน้ากาก latex/silicone: พึ่ง smile challenge ที่ server ตรวจซ้ำแล้ว แต่เกณฑ์วัดจากคนเดียว 2 คู่ภาพ ต้องดู `details.smile` จากคนอื่น ≥3 คนว่าไม่ false reject (ถ้าเจอ ลด `SMILE_MIN_WIDTH_GAIN`) ถ้าต้องการกันจริงต้องเทรน/หา model ที่ฝึกกับหน้ากาก หรือใช้ depth บน iPhone (ARKit) ซึ่งกัน silicone ไม่ได้เช่นกัน (1) ขั้น B: ทดสอบสดหน้ากล้อง (คนจริงผ่านทุกครั้ง? รูปพิมพ์เอียงไม่ผ่าน?) แล้วปรับ `parallaxMinShift` ถ้าจำเป็น; ML Kit ตรวจไม่เจอหน้าเล็กในมือถือที่ถือไกล (minFaceSize 0.15) จึงยังไม่มีตัวเลข replay ระยะไกล; screen-flash ยังไม่ทำ (2) CVPR gate วัดจากคนเดียว/มือถือเดียว/webcam เดียว margin ที่ใช้ได้แคบ (0.3 เท่านั้น) ต้องทดสอบคนอื่น ≥2 และจอใหญ่ (iPad/monitor) ก่อนไว้ใจ (3) iPhone จริงยังไม่เคยรัน: `yawSign` ใน mlkit_camera_source.dart และ box normalize บน iOS ยังไม่พิสูจน์ (4) Phase 3 calibrate กับสมาชิกอื่นยังไม่ทำ (scripts/calibrate.py พร้อม) (5) weights/cvpr2024/resnet50.onnx 94MB ไม่เข้า git ต้องรัน weights/convert_cvpr.py ในเครื่องใหม่ (6) อาจต้องย้าย tests/fixtures ที่มีหน้าผู้ใช้ออกจาก git ถ้าผู้ใช้ไม่ต้องการ
ค้นพบ: วิดีโอผ่าน active challenge ได้ทุกครั้ง ชั้น passive คือด่านหลัก · MiniFASNet ปฏิเสธจอเพราะ "เห็นขอบ" ถ้าไม่เห็นขอบให้ real 0.7–0.97 · CVPR model ต้องป้อน face crop (full frame โดนหลอก) และไวต่อ margin: 0.2 ปฏิเสธ frame จริงจาก iPhone 7/30, ≥0.4 ปล่อย replay · ยก MATCH_THRESHOLD ไม่ช่วยกับวิดีโอคนเดียวกัน (0.63–0.80 เท่าหน้าจริง) · MiniFASNet input BGR 0-255 ไม่หาร 255 · insightface yaw>0 = หันขวา · Android emulator ตัด webcam แนวนอนเป็นแนวตั้ง · port 8000 เคยถูกโปรเซสอื่นใช้ · Phase 4 แก้แล้วให้ขั้น B เป็น client-only ตามที่ผู้ใช้เลือก · ไฟล์ที่ adb push เข้า Android/data ของแอปอ่านไม่ได้ (permission) ต้อง `run-as <pkg> cp` เข้า /data/user/0/<pkg>/files
ถัดไป: /ship ทั้งชุด (parallax, screen-flash + locality, smile server-check, consistency pose, eval script) → ทดสอบกับคนอื่น/มือถืออื่น → ARKit depth บน iPhone เมื่อมีเครื่อง
