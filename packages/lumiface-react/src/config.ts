/** Tunables of the client-side liveness state machine. The server sends the project's values with every session. */
export interface LivenessConfig {
  alignHoldMs: number;
  minFaceWidthFraction: number;
  maxFaceWidthFraction: number;
  centerTolerance: number;
  neutralMaxYaw: number;
  neutralMaxPitch: number;
  challengeTimeoutMs: number;
  faceLostGraceMs: number;
  eyeOpenThreshold: number;
  eyeClosedThreshold: number;
  blinkMinMs: number;
  blinkMaxMs: number;
  smileThreshold: number;
  smileBaselineMax: number;
  smileHoldMs: number;
  turnMinYaw: number;
  turnHoldMs: number;
  parallaxMinShift: number;
  parallaxWhenNoTurn: boolean;
  nodMinPitch: number;
  nodHoldMs: number;
  settleAfterChallengeMs: number;
  settleAfterFlashMs: number;
}

export const DEFAULT_CONFIG: LivenessConfig = {
  alignHoldMs: 600,
  minFaceWidthFraction: 0.28,
  maxFaceWidthFraction: 0.75,
  centerTolerance: 0.18,
  neutralMaxYaw: 15,
  neutralMaxPitch: 15,
  challengeTimeoutMs: 10000,
  faceLostGraceMs: 1500,
  eyeOpenThreshold: 0.6,
  eyeClosedThreshold: 0.25,
  blinkMinMs: 40,
  blinkMaxMs: 600,
  smileThreshold: 0.7,
  smileBaselineMax: 0.4,
  smileHoldMs: 300,
  turnMinYaw: 25,
  turnHoldMs: 200,
  parallaxMinShift: 0.08,
  parallaxWhenNoTurn: true,
  nodMinPitch: 15,
  nodHoldMs: 200,
  settleAfterChallengeMs: 400,
  settleAfterFlashMs: 800,
};

const SNAKE_KEYS: Record<keyof LivenessConfig, string> = {
  alignHoldMs: "align_hold_ms",
  minFaceWidthFraction: "min_face_width_fraction",
  maxFaceWidthFraction: "max_face_width_fraction",
  centerTolerance: "center_tolerance",
  neutralMaxYaw: "neutral_max_yaw",
  neutralMaxPitch: "neutral_max_pitch",
  challengeTimeoutMs: "challenge_timeout_ms",
  faceLostGraceMs: "face_lost_grace_ms",
  eyeOpenThreshold: "eye_open_threshold",
  eyeClosedThreshold: "eye_closed_threshold",
  blinkMinMs: "blink_min_ms",
  blinkMaxMs: "blink_max_ms",
  smileThreshold: "smile_threshold",
  smileBaselineMax: "smile_baseline_max",
  smileHoldMs: "smile_hold_ms",
  turnMinYaw: "turn_min_yaw",
  turnHoldMs: "turn_hold_ms",
  parallaxMinShift: "parallax_min_shift",
  parallaxWhenNoTurn: "parallax_when_no_turn",
  nodMinPitch: "nod_min_pitch",
  nodHoldMs: "nod_hold_ms",
  settleAfterChallengeMs: "settle_after_challenge_ms",
  settleAfterFlashMs: "settle_after_flash_ms",
};

/** Parses the server's snake_case `client_config`; missing keys keep the defaults. */
export function configFromJson(json: Record<string, unknown> | null | undefined): LivenessConfig {
  const out: Record<string, unknown> = { ...DEFAULT_CONFIG };
  if (!json) return out as unknown as LivenessConfig;
  for (const [camel, snake] of Object.entries(SNAKE_KEYS)) {
    if (json[snake] !== undefined && json[snake] !== null) out[camel] = json[snake];
  }
  return out as unknown as LivenessConfig;
}

export function configToJson(config: LivenessConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [camel, snake] of Object.entries(SNAKE_KEYS)) out[snake] = config[camel as keyof LivenessConfig];
  return out;
}
