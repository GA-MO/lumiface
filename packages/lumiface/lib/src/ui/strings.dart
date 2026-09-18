import '../liveness/face_verify_controller.dart';
import '../models.dart';

/// User-facing texts. Defaults are English; [LivenessStrings.th] is Thai.
/// Use [copyWith] to change single lines, e.g. the success message per use case.
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
    this.liveSuccess = 'Live person confirmed',
    this.enrollSuccess = 'Photo enrolled',
    this.cameraError = 'Camera unavailable',
  });

  final String starting;
  final String uploading;
  final String success;
  final String liveSuccess;
  final String enrollSuccess;
  final String flashing;
  final String cameraError;
  final Map<AlignHint, String> hints;
  final Map<Challenge, String> challenges;
  final Map<String, String> reasons;
  final String retry;
  final String done;

  String reason(String code) => reasons[code] ?? code;

  String successFor(FaceFlow flow) => switch (flow) {
        FaceFlow.verify => success,
        FaceFlow.liveness => liveSuccess,
        FaceFlow.enroll => enrollSuccess,
      };

  /// Resolves the line to show for [state] in [flow].
  String messageFor(LivenessState state, FaceFlow flow) => switch (state.phase) {
        LivenessPhase.idle || LivenessPhase.starting => starting,
        LivenessPhase.aligning => hints[state.hint ?? AlignHint.noFace] ?? '',
        LivenessPhase.challenge => state.hint != null
            ? (hints[state.hint!] ?? '')
            : (challenges[state.challenge!] ?? state.challenge!.wire),
        LivenessPhase.flash => flashing,
        LivenessPhase.uploading => uploading,
        LivenessPhase.success => successFor(flow),
        LivenessPhase.failed => reason(state.result?.reasonCode ?? ''),
      };

  LivenessStrings copyWith({
    String? starting,
    String? uploading,
    String? success,
    String? liveSuccess,
    String? enrollSuccess,
    String? flashing,
    String? cameraError,
    Map<AlignHint, String>? hints,
    Map<Challenge, String>? challenges,
    Map<String, String>? reasons,
    String? retry,
    String? done,
  }) =>
      LivenessStrings(
        starting: starting ?? this.starting,
        uploading: uploading ?? this.uploading,
        success: success ?? this.success,
        liveSuccess: liveSuccess ?? this.liveSuccess,
        enrollSuccess: enrollSuccess ?? this.enrollSuccess,
        flashing: flashing ?? this.flashing,
        cameraError: cameraError ?? this.cameraError,
        hints: hints ?? this.hints,
        challenges: challenges ?? this.challenges,
        reasons: reasons == null ? this.reasons : {...this.reasons, ...reasons},
        retry: retry ?? this.retry,
        done: done ?? this.done,
      );

  static const en = LivenessStrings(
    starting: 'Preparing…',
    uploading: 'Verifying…',
    success: 'Verified',
    hints: {
      AlignHint.noFace: 'Position your face in the frame',
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
      'POSE_NOT_FRONTAL': 'Look straight at the camera',
      'TIMEOUT': 'Timed out, please try again',
      'FACE_LOST': 'Face left the frame',
      'NETWORK_ERROR': 'Cannot reach the server',
      'SESSION_EXPIRED': 'Session expired, please try again',
      'SUBJECT_NOT_FOUND': 'This person is not enrolled',
      'SUBJECT_EXISTS': 'This person is already enrolled',
      'NO_FACE': 'No face detected',
      'MULTIPLE_FACES': 'More than one face detected',
      'FACE_TOO_SMALL': 'Move closer to the camera',
      'TIMING_TOO_FAST': 'Please try again more slowly',
      'TIMING_TOO_SLOW': 'Too slow, please try again',
      'FLASH_FAIL': 'Could not confirm a live person (screen reflection)',
      'EXPRESSION_MISMATCH': 'Smile not detected, please try again',
      'CAPTURE_ERROR': 'Camera error, please try again',
      'CANCELLED': 'Cancelled',
    },
    retry: 'Try again',
    done: 'Done',
  );

  static const th = LivenessStrings(
    starting: 'กำลังเตรียม…',
    uploading: 'กำลังตรวจสอบ…',
    success: 'ยืนยันตัวตนสำเร็จ',
    liveSuccess: 'ยืนยันว่าเป็นบุคคลจริง',
    enrollSuccess: 'ลงทะเบียนใบหน้าแล้ว',
    cameraError: 'ใช้กล้องไม่ได้',
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
      'POSE_NOT_FRONTAL': 'มองตรงมาที่กล้อง',
      'TIMEOUT': 'หมดเวลา กรุณาลองใหม่',
      'FACE_LOST': 'ใบหน้าหลุดออกจากกรอบ',
      'NETWORK_ERROR': 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้',
      'SESSION_EXPIRED': 'หมดเวลา session กรุณาลองใหม่',
      'SUBJECT_NOT_FOUND': 'ยังไม่ได้ลงทะเบียนใบหน้า',
      'SUBJECT_EXISTS': 'ลงทะเบียนไว้แล้ว',
      'NO_FACE': 'ไม่พบใบหน้า',
      'MULTIPLE_FACES': 'พบใบหน้ามากกว่าหนึ่งคน',
      'FACE_TOO_SMALL': 'ขยับเข้าใกล้กล้องอีก',
      'TIMING_TOO_FAST': 'กรุณาทำช้าลงแล้วลองใหม่',
      'TIMING_TOO_SLOW': 'ช้าเกินไป กรุณาลองใหม่',
      'FLASH_FAIL': 'ไม่สามารถยืนยันบุคคลจริงได้ (แสงสะท้อนจากหน้าจอ)',
      'EXPRESSION_MISMATCH': 'ตรวจไม่พบรอยยิ้ม กรุณาลองใหม่',
      'CAPTURE_ERROR': 'กล้องมีปัญหา กรุณาลองใหม่',
      'CANCELLED': 'ยกเลิก',
    },
    retry: 'ลองใหม่',
    flashing: 'มองจอ อยู่นิ่งๆ…',
    done: 'เสร็จสิ้น',
  );
}
