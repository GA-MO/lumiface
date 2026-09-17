import 'dart:ui' show Rect;

/// Active-liveness challenges. Names match the server's challenge pool.
enum Challenge {
  blink,
  turnLeft,
  turnRight,
  smile,
  nod;

  static Challenge fromWire(String s) => switch (s) {
        'blink' => Challenge.blink,
        'turn_left' => Challenge.turnLeft,
        'turn_right' => Challenge.turnRight,
        'smile' => Challenge.smile,
        'nod' => Challenge.nod,
        _ => throw ArgumentError('unknown challenge $s'),
      };

  String get wire => switch (this) {
        Challenge.blink => 'blink',
        Challenge.turnLeft => 'turn_left',
        Challenge.turnRight => 'turn_right',
        Challenge.smile => 'smile',
        Challenge.nod => 'nod',
      };
}

/// One observation of the face in the camera stream. All fields except [tsMs]
/// and [faceCount] are null when no face is present.
///
/// [box] is normalised to the *upright* image (0..1 on both axes).
/// Angles are degrees; [yaw] positive = the user's own left (mirror-corrected
/// by the signal source so the controller never cares about camera facing).
class FaceSignal {
  const FaceSignal({
    required this.tsMs,
    required this.faceCount,
    this.box,
    this.eyeOpenLeft,
    this.eyeOpenRight,
    this.smile,
    this.yaw,
    this.pitch,
  });

  const FaceSignal.none(this.tsMs)
      : faceCount = 0,
        box = null,
        eyeOpenLeft = null,
        eyeOpenRight = null,
        smile = null,
        yaw = null,
        pitch = null;

  final int tsMs;
  final int faceCount;
  final Rect? box;
  final double? eyeOpenLeft;
  final double? eyeOpenRight;
  final double? smile;
  final double? yaw;
  final double? pitch;

  bool get present => faceCount == 1 && box != null;

  double? get eyeOpen => (eyeOpenLeft == null || eyeOpenRight == null)
      ? null
      : (eyeOpenLeft! + eyeOpenRight!) / 2;
}

class CheckinSession {
  const CheckinSession({
    required this.id,
    required this.challenges,
    required this.frameKinds,
    required this.ttlSeconds,
  });

  final String id;
  final List<Challenge> challenges;
  final List<String> frameKinds;
  final int ttlSeconds;

  factory CheckinSession.fromJson(Map<String, dynamic> j) => CheckinSession(
        id: j['session_id'] as String,
        challenges: (j['challenges'] as List).map((e) => Challenge.fromWire(e as String)).toList(),
        frameKinds: (j['frame_kinds'] as List).cast<String>(),
        ttlSeconds: j['ttl_seconds'] as int,
      );
}

class CapturedFrame {
  const CapturedFrame({required this.kind, required this.tsMs, required this.jpeg});

  final String kind;
  final int tsMs;
  final List<int> jpeg;
}

class CheckinScores {
  const CheckinScores({this.match, this.spoof, this.consistency});

  final double? match;
  final double? spoof;
  final double? consistency;

  factory CheckinScores.fromJson(Map<String, dynamic>? j) => CheckinScores(
        match: (j?['match'] as num?)?.toDouble(),
        spoof: (j?['spoof'] as num?)?.toDouble(),
        consistency: (j?['consistency'] as num?)?.toDouble(),
      );
}

/// Final outcome of a check-in attempt. [reasonCode] is either a server code
/// (OK, SPOOF, NO_MATCH, ...) or a client code (TIMEOUT, FACE_LOST, CANCELLED,
/// NETWORK_ERROR).
class CheckinResult {
  const CheckinResult({
    required this.ok,
    required this.reasonCode,
    this.scores = const CheckinScores(),
    this.checkinId,
    this.message,
  });

  final bool ok;
  final String reasonCode;
  final CheckinScores scores;
  final int? checkinId;
  final String? message;

  factory CheckinResult.fromJson(Map<String, dynamic> j) => CheckinResult(
        ok: j['ok'] as bool,
        reasonCode: j['reason_code'] as String,
        scores: CheckinScores.fromJson(j['scores'] as Map<String, dynamic>?),
        checkinId: j['checkin_id'] as int?,
      );

  factory CheckinResult.clientError(String code, [String? message]) =>
      CheckinResult(ok: false, reasonCode: code, message: message);
}

class Employee {
  const Employee({required this.externalId, required this.name, required this.enrollSpoofScore});

  final String externalId;
  final String name;
  final double enrollSpoofScore;

  factory Employee.fromJson(Map<String, dynamic> j) => Employee(
        externalId: j['external_id'] as String,
        name: (j['name'] as String?) ?? '',
        enrollSpoofScore: (j['enroll_spoof_score'] as num).toDouble(),
      );
}

class CheckinRecord {
  const CheckinRecord({
    required this.id,
    required this.employeeId,
    required this.ok,
    required this.reasonCode,
    required this.createdAt,
    this.scores = const CheckinScores(),
  });

  final int id;
  final String employeeId;
  final bool ok;
  final String reasonCode;
  final DateTime createdAt;
  final CheckinScores scores;

  factory CheckinRecord.fromJson(Map<String, dynamic> j) => CheckinRecord(
        id: j['id'] as int,
        employeeId: j['employee_id'] as String,
        ok: j['ok'] as bool,
        reasonCode: j['reason_code'] as String,
        createdAt: DateTime.parse(j['created_at'] as String),
        scores: CheckinScores(
          match: (j['match_score'] as num?)?.toDouble(),
          spoof: (j['spoof_score'] as num?)?.toDouble(),
          consistency: (j['consistency_score'] as num?)?.toDouble(),
        ),
      );
}

class EnrollException implements Exception {
  EnrollException(this.reasonCode, [this.details]);
  final String reasonCode;
  final Map<String, dynamic>? details;
  @override
  String toString() => 'EnrollException($reasonCode)';
}
