import 'dart:ui' show Color, Offset, Rect;

import 'liveness/config.dart';

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

/// What a session proves: `verify` matches an enrolled subject, `liveness`
/// only proves a live person, `enroll` captures a frontal photo for enrolment.
enum FaceFlow { verify, liveness, enroll }

/// One observation of the face in the camera stream. All fields except [tsMs]
/// and [faceCount] are null when no face is present.
///
/// [box], [nose], [leftEye] and [rightEye] are normalised to the *upright*
/// image (0..1 on both axes). Angles are degrees; [yaw] positive = the user's
/// own left (mirror-corrected by the signal source so the controller never
/// cares about camera facing).
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
    this.nose,
    this.leftEye,
    this.rightEye,
  });

  const FaceSignal.none(this.tsMs)
    : faceCount = 0,
      box = null,
      eyeOpenLeft = null,
      eyeOpenRight = null,
      smile = null,
      yaw = null,
      pitch = null,
      nose = null,
      leftEye = null,
      rightEye = null;

  final int tsMs;
  final int faceCount;
  final Rect? box;
  final double? eyeOpenLeft;
  final double? eyeOpenRight;
  final double? smile;
  final double? yaw;
  final double? pitch;
  final Offset? nose;
  final Offset? leftEye;
  final Offset? rightEye;

  bool get present => faceCount == 1 && box != null;

  double? get eyeOpen => (eyeOpenLeft == null || eyeOpenRight == null) ? null : (eyeOpenLeft! + eyeOpenRight!) / 2;

  /// Horizontal offset of the nose base from the eye midpoint, in units of
  /// inter-eye distance. Stays constant when a flat picture is rotated; shifts
  /// with yaw on a real (3D) face because the nose sits in front of the eyes.
  double? get noseParallax {
    if (nose == null || leftEye == null || rightEye == null) return null;
    final dist = (rightEye!.dx - leftEye!.dx).abs();
    if (dist < 1e-4) return null;
    return (nose!.dx - (leftEye!.dx + rightEye!.dx) / 2) / dist;
  }
}

/// A verification session issued by the server. Carries the challenges, the
/// screen-flash colours and the client tunables of the project's policy.
/// What the backend hands the device. The plan (challenges, colours) only arrives over the stream.
class FaceSession {
  const FaceSession({
    required this.id,
    required this.ttlSeconds,
    this.token = '',
    this.mode = 'verify',
    this.purpose = '',
    this.clientConfig,
  });

  final String id;

  /// Bearer secret good for this session's stream only.
  final String token;
  final String mode;
  final String purpose;
  final int ttlSeconds;

  /// Client tunables from the project's policy, null on servers that predate it.
  final LivenessConfig? clientConfig;

  factory FaceSession.fromJson(Map<String, dynamic> j) => FaceSession(
    id: j['session_id'] as String,
    token: (j['session_token'] as String?) ?? '',
    mode: (j['mode'] as String?) ?? 'verify',
    purpose: (j['purpose'] as String?) ?? '',
    ttlSeconds: j['ttl_seconds'] as int,
    clientConfig: j['client_config'] is Map
        ? LivenessConfig.fromJson((j['client_config'] as Map).cast<String, dynamic>())
        : null,
  );
}

/// The server's first message on the stream: what to do, decided server-side for this session.
class StreamPlan {
  const StreamPlan({required this.challenges, this.flashColors = const [], this.flashHoldMs = 450, this.clientConfig});

  final List<Challenge> challenges;

  /// Screen-flash sequence: the screen is filled with each colour in turn. Empty when disabled.
  final List<Color> flashColors;
  final int flashHoldMs;
  final LivenessConfig? clientConfig;

  factory StreamPlan.fromJson(Map<String, dynamic> j) => StreamPlan(
    challenges: ((j['challenges'] as List?) ?? const []).map((e) => Challenge.fromWire(e as String)).toList(),
    flashColors: [
      for (final h in (j['flash_colors'] as List?)?.cast<String>() ?? const <String>[])
        Color(0xFF000000 | int.parse(h, radix: 16)),
    ],
    flashHoldMs: (j['flash_hold_ms'] as int?) ?? 450,
    clientConfig: j['client_config'] is Map
        ? LivenessConfig.fromJson((j['client_config'] as Map).cast<String, dynamic>())
        : null,
  );
}

enum StreamEventName { aligned, challengeDone, flash, flashEnd }

class VerifyScores {
  const VerifyScores({this.match, this.spoof, this.consistency});

  final double? match;
  final double? spoof;
  final double? consistency;

  factory VerifyScores.fromJson(Map<String, dynamic>? j) => VerifyScores(
    match: (j?['match'] as num?)?.toDouble(),
    spoof: (j?['spoof'] as num?)?.toDouble(),
    consistency: (j?['consistency'] as num?)?.toDouble(),
  );
}

/// Final outcome of a flow. [reasonCode] is either a server code
/// (OK, SPOOF, NO_MATCH, ...) or a client code (TIMEOUT, FACE_LOST, CANCELLED,
/// NETWORK_ERROR, CAPTURE_ERROR).
class VerifyResult {
  const VerifyResult({
    required this.ok,
    required this.reasonCode,
    this.mode = 'verify',
    this.scores = const VerifyScores(),
    this.verificationId,
    this.sessionId,
    this.subject,
    this.message,
  });

  final bool ok;
  final String mode;
  final String reasonCode;
  final VerifyScores scores;
  final int? verificationId;

  /// The session this result belongs to; hand it to your backend, which reads
  /// the outcome with `GET /v1/sessions/{id}` instead of trusting this object.
  final String? sessionId;

  /// Set by the enrol flow when the photo was accepted.
  final Subject? subject;
  final String? message;

  factory VerifyResult.fromJson(Map<String, dynamic> j) => VerifyResult(
    ok: j['ok'] as bool,
    mode: (j['mode'] as String?) ?? 'verify',
    reasonCode: j['reason_code'] as String,
    scores: VerifyScores.fromJson(j['scores'] as Map<String, dynamic>?),
    verificationId: j['verification_id'] as int?,
    sessionId: j['session_id'] as String?,
  );

  factory VerifyResult.clientError(String code, [String? message]) =>
      VerifyResult(ok: false, reasonCode: code, message: message);

  VerifyResult withSession(String sessionId) => VerifyResult(
    ok: ok,
    reasonCode: reasonCode,
    mode: mode,
    scores: scores,
    verificationId: verificationId,
    sessionId: sessionId,
    subject: subject,
    message: message,
  );

  factory VerifyResult.enrolled(Subject subject) =>
      VerifyResult(ok: true, mode: 'enroll', reasonCode: 'OK', subject: subject);
}

class Subject {
  const Subject({required this.externalId, required this.name, required this.enrollSpoofScore, this.expiresAt});

  final String externalId;
  final String name;
  final double enrollSpoofScore;

  /// When the server drops the embedding; null keeps it until deleted.
  final DateTime? expiresAt;

  factory Subject.fromJson(Map<String, dynamic> j) => Subject(
    externalId: j['external_id'] as String,
    name: (j['name'] as String?) ?? '',
    enrollSpoofScore: (j['enroll_spoof_score'] as num).toDouble(),
    expiresAt: j['expires_at'] == null ? null : DateTime.parse(j['expires_at'] as String),
  );
}

class VerificationRecord {
  const VerificationRecord({
    required this.id,
    this.sessionId = '',
    required this.subjectId,
    required this.purpose,
    required this.ok,
    required this.reasonCode,
    required this.createdAt,
    this.scores = const VerifyScores(),
  });

  final int id;
  final String sessionId;
  final String? subjectId;
  final String purpose;
  final bool ok;
  final String reasonCode;
  final DateTime createdAt;
  final VerifyScores scores;

  factory VerificationRecord.fromJson(Map<String, dynamic> j) => VerificationRecord(
    id: j['id'] as int,
    sessionId: (j['session_id'] as String?) ?? '',
    subjectId: j['subject_id'] as String?,
    purpose: (j['purpose'] as String?) ?? '',
    ok: j['ok'] as bool,
    reasonCode: j['reason_code'] as String,
    createdAt: DateTime.parse(j['created_at'] as String),
    scores: VerifyScores(
      match: (j['match_score'] as num?)?.toDouble(),
      spoof: (j['spoof_score'] as num?)?.toDouble(),
      consistency: (j['consistency_score'] as num?)?.toDouble(),
    ),
  );
}

/// A project's verification policy as the server reports it.
class ProjectPolicy {
  const ProjectPolicy({required this.project, required this.preset, required this.overrides, required this.effective});

  final String project;
  final String preset;
  final Map<String, dynamic> overrides;
  final Map<String, dynamic> effective;

  LivenessConfig get clientConfig => LivenessConfig.fromJson((effective['client'] as Map).cast<String, dynamic>());

  factory ProjectPolicy.fromJson(Map<String, dynamic> j) => ProjectPolicy(
    project: j['project'] as String,
    preset: j['preset'] as String,
    overrides: (j['overrides'] as Map).cast<String, dynamic>(),
    effective: (j['effective'] as Map).cast<String, dynamic>(),
  );
}

class PolicyPreset {
  const PolicyPreset({required this.name, required this.summary, required this.overrides});

  final String name;
  final String summary;
  final Map<String, dynamic> overrides;

  factory PolicyPreset.fromJson(Map<String, dynamic> j) => PolicyPreset(
    name: j['name'] as String,
    summary: j['summary'] as String,
    overrides: (j['overrides'] as Map).cast<String, dynamic>(),
  );
}

class LumifaceException implements Exception {
  LumifaceException(this.reasonCode, [this.details]);
  final String reasonCode;
  final Map<String, dynamic>? details;
  @override
  String toString() => 'LumifaceException($reasonCode)';
}
