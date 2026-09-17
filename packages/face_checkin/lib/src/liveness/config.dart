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
    this.nodMinPitch = 15,
    this.nodHoldMs = 200,
    this.settleAfterChallengeMs = 400,
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
  final double nodMinPitch;
  final int nodHoldMs;
  final int settleAfterChallengeMs;
}
