## 0.2.0

- Renamed from `face_checkin` to `facegate`; `CheckinApi` → `FacegateClient`, employees → subjects, check-ins → verifications.
- `FaceVerifyView` replaces `FaceCheckinScreen`: flows (`verify`, `liveness`, `enroll`), `FaceVerifyTheme`, builder slots, `overlayBuilder`, `sourceFactory`, `onStateChanged`, `onController`.
- Headless `FaceVerifyController` (subject optional, `purpose`) and `FaceEnrollController`.
- `LivenessConfig.fromJson` / `toJson`; the session's `client_config` is applied automatically.
- Web support through `MediaPipeCameraSource` (Phase 5).
- `LivenessStrings.copyWith`, `messageFor`, per-flow success lines, more reason codes.

## 0.0.1

- Initial check-in screen with ML Kit, screen flash and parallax.
