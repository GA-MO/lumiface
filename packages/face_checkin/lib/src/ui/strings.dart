import '../liveness/liveness_controller.dart';
import '../models.dart';

/// User-facing texts. Defaults are English; [LivenessStrings.th] is Thai.
class LivenessStrings {
  const LivenessStrings({
    required this.starting,
    required this.uploading,
    required this.success,
    required this.hints,
    required this.challenges,
    required this.reasons,
    required this.retry,
    required this.done,
    this.flashing = 'Hold still…',
  });

  final String starting;
  final String uploading;
  final String success;
  final String flashing;
  final Map<AlignHint, String> hints;
  final Map<Challenge, String> challenges;
  final Map<String, String> reasons;
  final String retry;
  final String done;

  String reason(String code) => reasons[code] ?? code;

  static const en = LivenessStrings(
    starting: 'Preparing…',
    uploading: 'Verifying…',
    success: 'Checked in',
    hints: {
      AlignHint.noFace: 'Position your face in the oval',
      AlignHint.multipleFaces: 'Only one face please',
      AlignHint.tooFar: 'Move closer',
      AlignHint.tooClose: 'Move back a little',
      AlignHint.notCentered: 'Center your face',
      AlignHint.lookStraight: 'Look straight at the camera',
      AlignHint.holdStill: 'Hold still…',
    },
    challenges: {
      Challenge.blink: 'Blink',
      Challenge.smile: 'Smile',
      Challenge.turnLeft: 'Turn your head left',
      Challenge.turnRight: 'Turn your head right',
      Challenge.nod: 'Nod your head',
    },
    reasons: {
      'SPOOF': 'Could not confirm a live person',
      'NO_MATCH': 'Face does not match the registered photo',
      'INCONSISTENT': 'Face changed during the check',
      'POSE_MISMATCH': 'Head movement not detected',
      'TIMEOUT': 'Timed out, please try again',
      'FACE_LOST': 'Face left the frame',
      'NETWORK_ERROR': 'Cannot reach the server',
      'SESSION_EXPIRED': 'Session expired, please try again',
      'NO_FACE': 'No face detected',
      'MULTIPLE_FACES': 'More than one face detected',
      'FACE_TOO_SMALL': 'Move closer to the camera',
      'TIMING_TOO_FAST': 'Please try again more slowly',
      'FLASH_FAIL': 'Could not confirm a live person (screen reflection)',
      'EXPRESSION_MISMATCH': 'Smile not detected, please try again',
      'CANCELLED': 'Cancelled',
    },
    retry: 'Try again',
    done: 'Done',
  );

  static const th = LivenessStrings(
    starting: 'กำลังเตรียม…',
    uploading: 'กำลังตรวจสอบ…',
    success: 'เช็คอินสำเร็จ',
    hints: {
      AlignHint.noFace: 'วางใบหน้าให้อยู่ในกรอบ',
      AlignHint.multipleFaces: 'ต้องมีใบหน้าเดียวในกรอบ',
      AlignHint.tooFar: 'ขยับเข้าใกล้กล้อง',
      AlignHint.tooClose: 'ถอยออกเล็กน้อย',
      AlignHint.notCentered: 'จัดใบหน้าให้อยู่กลางกรอบ',
      AlignHint.lookStraight: 'มองตรงมาที่กล้อง',
      AlignHint.holdStill: 'อยู่นิ่งๆ สักครู่…',
    },
    challenges: {
      Challenge.blink: 'กะพริบตา',
      Challenge.smile: 'ยิ้ม',
      Challenge.turnLeft: 'หันหน้าไปทางซ้าย',
      Challenge.turnRight: 'หันหน้าไปทางขวา',
      Challenge.nod: 'พยักหน้า',
    },
    reasons: {
      'SPOOF': 'ไม่สามารถยืนยันได้ว่าเป็นบุคคลจริง',
      'NO_MATCH': 'ใบหน้าไม่ตรงกับรูปที่ลงทะเบียน',
      'INCONSISTENT': 'ใบหน้าเปลี่ยนระหว่างการตรวจ',
      'POSE_MISMATCH': 'ตรวจไม่พบการขยับศีรษะ',
      'TIMEOUT': 'หมดเวลา กรุณาลองใหม่',
      'FACE_LOST': 'ใบหน้าหลุดออกจากกรอบ',
      'NETWORK_ERROR': 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้',
      'SESSION_EXPIRED': 'หมดเวลา session กรุณาลองใหม่',
      'NO_FACE': 'ไม่พบใบหน้า',
      'MULTIPLE_FACES': 'พบใบหน้ามากกว่าหนึ่งคน',
      'FACE_TOO_SMALL': 'ขยับเข้าใกล้กล้องอีก',
      'TIMING_TOO_FAST': 'กรุณาทำช้าลงแล้วลองใหม่',
      'FLASH_FAIL': 'ไม่สามารถยืนยันบุคคลจริงได้ (แสงสะท้อนจากหน้าจอ)',
      'EXPRESSION_MISMATCH': 'ตรวจไม่พบรอยยิ้ม กรุณาลองใหม่',
      'CANCELLED': 'ยกเลิก',
    },
    retry: 'ลองใหม่',
    flashing: 'มองจอ อยู่นิ่งๆ…',
    done: 'เสร็จสิ้น',
  );
}
