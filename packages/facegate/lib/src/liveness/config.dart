/// Tunables for the client-side active-liveness state machine.
///
/// The server sends the project's values with every session
/// (`client_config`); pass an instance explicitly only to override them.
class LivenessConfig {
  const LivenessConfig({
    this.alignHoldMs = 600,
    this.minFaceWidthFraction = 0.28,
    this.maxFaceWidthFraction = 0.75,
    this.centerTolerance = 0.18,
    this.neutralMaxYaw = 15,
    this.neutralMaxPitch = 15,
    this.challengeTimeoutMs = 10000,
    this.faceLostGraceMs = 1500,
    this.eyeOpenThreshold = 0.6,
    this.eyeClosedThreshold = 0.25,
    this.blinkMinMs = 40,
    this.blinkMaxMs = 600,
    this.smileThreshold = 0.7,
    this.smileBaselineMax = 0.4,
    this.smileHoldMs = 300,
    this.turnMinYaw = 25,
    this.turnHoldMs = 200,
    this.parallaxMinShift = 0.08,
    this.parallaxWhenNoTurn = true,
    this.nodMinPitch = 15,
    this.nodHoldMs = 200,
    this.settleAfterChallengeMs = 400,
    this.settleAfterFlashMs = 800,
  });

  final int alignHoldMs;
  final double minFaceWidthFraction;
  final double maxFaceWidthFraction;
  final double centerTolerance;
  final double neutralMaxYaw;
  final double neutralMaxPitch;
  final int challengeTimeoutMs;
  final int faceLostGraceMs;
  final double eyeOpenThreshold;
  final double eyeClosedThreshold;
  final int blinkMinMs;
  final int blinkMaxMs;
  final double smileThreshold;
  final double smileBaselineMax;
  final int smileHoldMs;
  final double turnMinYaw;
  final int turnHoldMs;

  /// Minimum change of [FaceSignal.noseParallax] between the frontal baseline
  /// and the turned pose for a turn to count. A flat picture (print or screen)
  /// rotated in front of the camera keeps the ratio ~constant; a real face at
  /// 25° yaw shifts it by roughly 0.15. Set to 0 to disable.
  final double parallaxMinShift;

  /// When the server picked no turn challenge, append a client-only turn so
  /// every session includes one parallax check. No frame is uploaded for it.
  final bool parallaxWhenNoTurn;
  final double nodMinPitch;
  final int nodHoldMs;
  final int settleAfterChallengeMs;

  /// Wait after the last flash colour before capturing neutral_end, so the
  /// screen tint has left the face and auto-exposure has recovered.
  final int settleAfterFlashMs;

  /// Parses the server's `client_config` (snake_case). Missing keys keep defaults.
  factory LivenessConfig.fromJson(Map<String, dynamic> j) {
    const d = LivenessConfig();
    int i(String k, int fallback) => (j[k] as num?)?.toInt() ?? fallback;
    double f(String k, double fallback) => (j[k] as num?)?.toDouble() ?? fallback;
    return LivenessConfig(
      alignHoldMs: i('align_hold_ms', d.alignHoldMs),
      minFaceWidthFraction: f('min_face_width_fraction', d.minFaceWidthFraction),
      maxFaceWidthFraction: f('max_face_width_fraction', d.maxFaceWidthFraction),
      centerTolerance: f('center_tolerance', d.centerTolerance),
      neutralMaxYaw: f('neutral_max_yaw', d.neutralMaxYaw),
      neutralMaxPitch: f('neutral_max_pitch', d.neutralMaxPitch),
      challengeTimeoutMs: i('challenge_timeout_ms', d.challengeTimeoutMs),
      faceLostGraceMs: i('face_lost_grace_ms', d.faceLostGraceMs),
      eyeOpenThreshold: f('eye_open_threshold', d.eyeOpenThreshold),
      eyeClosedThreshold: f('eye_closed_threshold', d.eyeClosedThreshold),
      blinkMinMs: i('blink_min_ms', d.blinkMinMs),
      blinkMaxMs: i('blink_max_ms', d.blinkMaxMs),
      smileThreshold: f('smile_threshold', d.smileThreshold),
      smileBaselineMax: f('smile_baseline_max', d.smileBaselineMax),
      smileHoldMs: i('smile_hold_ms', d.smileHoldMs),
      turnMinYaw: f('turn_min_yaw', d.turnMinYaw),
      turnHoldMs: i('turn_hold_ms', d.turnHoldMs),
      parallaxMinShift: f('parallax_min_shift', d.parallaxMinShift),
      parallaxWhenNoTurn: (j['parallax_when_no_turn'] as bool?) ?? d.parallaxWhenNoTurn,
      nodMinPitch: f('nod_min_pitch', d.nodMinPitch),
      nodHoldMs: i('nod_hold_ms', d.nodHoldMs),
      settleAfterChallengeMs: i('settle_after_challenge_ms', d.settleAfterChallengeMs),
      settleAfterFlashMs: i('settle_after_flash_ms', d.settleAfterFlashMs),
    );
  }

  Map<String, dynamic> toJson() => {
        'align_hold_ms': alignHoldMs,
        'min_face_width_fraction': minFaceWidthFraction,
        'max_face_width_fraction': maxFaceWidthFraction,
        'center_tolerance': centerTolerance,
        'neutral_max_yaw': neutralMaxYaw,
        'neutral_max_pitch': neutralMaxPitch,
        'challenge_timeout_ms': challengeTimeoutMs,
        'face_lost_grace_ms': faceLostGraceMs,
        'eye_open_threshold': eyeOpenThreshold,
        'eye_closed_threshold': eyeClosedThreshold,
        'blink_min_ms': blinkMinMs,
        'blink_max_ms': blinkMaxMs,
        'smile_threshold': smileThreshold,
        'smile_baseline_max': smileBaselineMax,
        'smile_hold_ms': smileHoldMs,
        'turn_min_yaw': turnMinYaw,
        'turn_hold_ms': turnHoldMs,
        'parallax_min_shift': parallaxMinShift,
        'parallax_when_no_turn': parallaxWhenNoTurn,
        'nod_min_pitch': nodMinPitch,
        'nod_hold_ms': nodHoldMs,
        'settle_after_challenge_ms': settleAfterChallengeMs,
        'settle_after_flash_ms': settleAfterFlashMs,
      };

  LivenessConfig copyWith({
    int? alignHoldMs,
    double? minFaceWidthFraction,
    double? maxFaceWidthFraction,
    double? centerTolerance,
    double? neutralMaxYaw,
    double? neutralMaxPitch,
    int? challengeTimeoutMs,
    int? faceLostGraceMs,
    double? eyeOpenThreshold,
    double? eyeClosedThreshold,
    int? blinkMinMs,
    int? blinkMaxMs,
    double? smileThreshold,
    double? smileBaselineMax,
    int? smileHoldMs,
    double? turnMinYaw,
    int? turnHoldMs,
    double? parallaxMinShift,
    bool? parallaxWhenNoTurn,
    double? nodMinPitch,
    int? nodHoldMs,
    int? settleAfterChallengeMs,
    int? settleAfterFlashMs,
  }) =>
      LivenessConfig(
        alignHoldMs: alignHoldMs ?? this.alignHoldMs,
        minFaceWidthFraction: minFaceWidthFraction ?? this.minFaceWidthFraction,
        maxFaceWidthFraction: maxFaceWidthFraction ?? this.maxFaceWidthFraction,
        centerTolerance: centerTolerance ?? this.centerTolerance,
        neutralMaxYaw: neutralMaxYaw ?? this.neutralMaxYaw,
        neutralMaxPitch: neutralMaxPitch ?? this.neutralMaxPitch,
        challengeTimeoutMs: challengeTimeoutMs ?? this.challengeTimeoutMs,
        faceLostGraceMs: faceLostGraceMs ?? this.faceLostGraceMs,
        eyeOpenThreshold: eyeOpenThreshold ?? this.eyeOpenThreshold,
        eyeClosedThreshold: eyeClosedThreshold ?? this.eyeClosedThreshold,
        blinkMinMs: blinkMinMs ?? this.blinkMinMs,
        blinkMaxMs: blinkMaxMs ?? this.blinkMaxMs,
        smileThreshold: smileThreshold ?? this.smileThreshold,
        smileBaselineMax: smileBaselineMax ?? this.smileBaselineMax,
        smileHoldMs: smileHoldMs ?? this.smileHoldMs,
        turnMinYaw: turnMinYaw ?? this.turnMinYaw,
        turnHoldMs: turnHoldMs ?? this.turnHoldMs,
        parallaxMinShift: parallaxMinShift ?? this.parallaxMinShift,
        parallaxWhenNoTurn: parallaxWhenNoTurn ?? this.parallaxWhenNoTurn,
        nodMinPitch: nodMinPitch ?? this.nodMinPitch,
        nodHoldMs: nodHoldMs ?? this.nodHoldMs,
        settleAfterChallengeMs: settleAfterChallengeMs ?? this.settleAfterChallengeMs,
        settleAfterFlashMs: settleAfterFlashMs ?? this.settleAfterFlashMs,
      );
}
