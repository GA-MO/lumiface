/// Tunables for the client-side active-liveness state machine.
///
/// The server sends the project's values with every session
/// (`client_config`); pass an instance explicitly only to override them.
class LivenessConfig {
  const LivenessConfig({
    this.alignHoldMs = 600,
    this.minFaceWidthFraction = 0.28,
    this.maxFaceWidthFraction = 0.48,
    this.centerTolerance = 0.18,
    this.neutralMaxYaw = 15,
    this.neutralMaxPitch = 15,
    this.challengeTimeoutMs = 10000,
    this.faceLostGraceMs = 1500,
    this.ovalMinFill = 0.85,
    this.ovalHoldMs = 500,
    this.moveStartMaxRatio = 0.8,
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

  final int settleAfterChallengeMs;

  /// face_move: face width / oval width that counts as fitted (centred within a fifth of the oval).
  final double ovalMinFill;

  /// face_move: the face must stay fitted this long.
  final int ovalHoldMs;

  /// face_move: the face width over the oval width the challenge must start below (come from far).
  final double moveStartMaxRatio;

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
      settleAfterChallengeMs: i('settle_after_challenge_ms', d.settleAfterChallengeMs),
      settleAfterFlashMs: i('settle_after_flash_ms', d.settleAfterFlashMs),
      ovalMinFill: f('oval_min_fill', d.ovalMinFill),
      ovalHoldMs: i('oval_hold_ms', d.ovalHoldMs),
      moveStartMaxRatio: f('move_start_max_ratio', d.moveStartMaxRatio),
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
        'settle_after_challenge_ms': settleAfterChallengeMs,
        'settle_after_flash_ms': settleAfterFlashMs,
        'oval_min_fill': ovalMinFill,
        'oval_hold_ms': ovalHoldMs,
        'move_start_max_ratio': moveStartMaxRatio,
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
    int? settleAfterChallengeMs,
    int? settleAfterFlashMs,
    double? ovalMinFill,
    int? ovalHoldMs,
    double? moveStartMaxRatio,
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
                                  settleAfterChallengeMs: settleAfterChallengeMs ?? this.settleAfterChallengeMs,
        settleAfterFlashMs: settleAfterFlashMs ?? this.settleAfterFlashMs,
        ovalMinFill: ovalMinFill ?? this.ovalMinFill,
        ovalHoldMs: ovalHoldMs ?? this.ovalHoldMs,
        moveStartMaxRatio: moveStartMaxRatio ?? this.moveStartMaxRatio,
      );
}
