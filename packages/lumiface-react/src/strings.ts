import type { AlignHint, LivenessState } from "./controller.ts";
import type { Challenge, FaceFlow } from "./types.ts";

export interface LivenessStrings {
  starting: string;
  uploading: string;
  success: string;
  liveSuccess: string;
  flashing: string;
  cameraError: string;
  hints: Record<AlignHint, string>;
  challenges: Record<Challenge, string>;
  reasons: Record<string, string>;
  retry: string;
  done: string;
}

export const EN: LivenessStrings = {
  starting: "Preparing…",
  uploading: "Verifying…",
  success: "Verified",
  liveSuccess: "Live person confirmed",
  flashing: "Hold still…",
  cameraError: "Camera unavailable",
  hints: {
    noFace: "Position your face in the frame",
    multipleFaces: "Only one face please",
    tooFar: "Move closer",
    tooClose: "Move back a little",
    notCentered: "Center your face",
    lookStraight: "Look straight at the camera",
    holdStill: "Hold still…",
  },
  challenges: {
    face_move: "Move closer until your face fills the oval",
  },
  reasons: {
    SPOOF: "Could not confirm a live person",
    NO_MATCH: "Face does not match the registered photo",
    INCONSISTENT: "Face changed during the check",
    MOVEMENT_MISMATCH: "Move closer into the oval, please try again",
    POSE_NOT_FRONTAL: "Look straight at the camera",
    TIMEOUT: "Timed out, please try again",
    FACE_LOST: "Face left the frame",
    NETWORK_ERROR: "Cannot reach the server",
    SESSION_EXPIRED: "Session expired, please try again",
    NO_FACE: "No face detected",
    MULTIPLE_FACES: "More than one face detected",
    FACE_TOO_SMALL: "Move closer to the camera",
    TIMING_TOO_FAST: "Please try again more slowly",
    TIMING_TOO_SLOW: "Too slow, please try again",
    FLASH_FAIL: "Could not confirm a live person (screen reflection)",
    CAPTURE_ERROR: "Camera error, please try again",
    CANCELLED: "Cancelled",
  },
  retry: "Try again",
  done: "Done",
};

export const TH: LivenessStrings = {
  ...EN,
  starting: "กำลังเตรียม…",
  uploading: "กำลังตรวจสอบ…",
  success: "ยืนยันตัวตนสำเร็จ",
  liveSuccess: "ยืนยันว่าเป็นบุคคลจริง",
  flashing: "มองจอ อยู่นิ่งๆ…",
  cameraError: "ใช้กล้องไม่ได้",
  hints: {
    noFace: "วางใบหน้าให้อยู่ในกรอบ",
    multipleFaces: "ต้องมีใบหน้าเดียวในกรอบ",
    tooFar: "ขยับเข้าใกล้กล้อง",
    tooClose: "ถอยออกเล็กน้อย",
    notCentered: "จัดใบหน้าให้อยู่กลางกรอบ",
    lookStraight: "มองตรงมาที่กล้อง",
    holdStill: "อยู่นิ่งๆ สักครู่…",
  },
  challenges: {
    face_move: "ขยับเข้ามาให้ใบหน้าเต็มวงรี",
  },
  reasons: {
    ...EN.reasons,
    SPOOF: "ไม่สามารถยืนยันได้ว่าเป็นบุคคลจริง",
    NO_MATCH: "ใบหน้าไม่ตรงกับรูปที่ลงทะเบียน",
    INCONSISTENT: "ใบหน้าเปลี่ยนระหว่างการตรวจ",
    MOVEMENT_MISMATCH: "ขยับเข้ามาให้เต็มวงรี กรุณาลองใหม่",
    TIMEOUT: "หมดเวลา กรุณาลองใหม่",
    FACE_LOST: "ใบหน้าหลุดออกจากกรอบ",
    NETWORK_ERROR: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้",
    NO_FACE: "ไม่พบใบหน้า",
    FLASH_FAIL: "ไม่สามารถยืนยันบุคคลจริงได้ (แสงสะท้อนจากหน้าจอ)",
    CANCELLED: "ยกเลิก",
  },
  retry: "ลองใหม่",
  done: "เสร็จสิ้น",
};

export function successFor(strings: LivenessStrings, flow: FaceFlow): string {
  return flow === "verify" ? strings.success : strings.liveSuccess;
}

/** The line to show for a state in a flow. */
export function messageFor(strings: LivenessStrings, state: LivenessState, flow: FaceFlow): string {
  switch (state.phase) {
    case "idle":
    case "starting":
      return strings.starting;
    case "aligning":
      return strings.hints[state.hint ?? "noFace"];
    case "challenge":
      return state.hint ? strings.hints[state.hint] : strings.challenges[state.challenge ?? "face_move"];
    case "flash":
      return strings.flashing;
    case "uploading":
      return strings.uploading;
    case "success":
      return successFor(strings, flow);
    case "failed": {
      const code = state.result?.reasonCode ?? "";
      return strings.reasons[code] ?? code;
    }
  }
}

/** Merges partial overrides (nested maps merge key by key) into a base strings set. */
export function mergeStrings(base: LivenessStrings, patch: Partial<LivenessStrings>): LivenessStrings {
  return {
    ...base,
    ...patch,
    hints: { ...base.hints, ...patch.hints },
    challenges: { ...base.challenges, ...patch.challenges },
    reasons: { ...base.reasons, ...patch.reasons },
  };
}
