/// Tunables for the client-side active-liveness state machine.
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
  /// screen tint has left the face and auto-exposure has recovered (measured on
  /// a Galaxy S25+: a frame taken 160-270 ms later was still tinted and scored
  /// 0.2-0.7 on MiniFASNet).
  final int settleAfterFlashMs;
}
