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
  settleAfterChallengeMs: number;
  settleAfterFlashMs: number;
  /** face_move: face width / oval width that counts as fitted (centred within a fifth of the oval). */
  ovalMinFill: number;
  /** face_move: the face must stay fitted this long. */
  ovalHoldMs: number;
  /** face_move: face width / oval width the challenge must start below (come from far). */
  moveStartMaxRatio: number;
}

export const DEFAULT_CONFIG: LivenessConfig = {
  alignHoldMs: 600,
  minFaceWidthFraction: 0.28,
  maxFaceWidthFraction: 0.48,
  centerTolerance: 0.18,
  neutralMaxYaw: 15,
  neutralMaxPitch: 15,
  challengeTimeoutMs: 10000,
  faceLostGraceMs: 1500,
  settleAfterChallengeMs: 400,
  settleAfterFlashMs: 800,
  ovalMinFill: 0.85,
  ovalHoldMs: 500,
  moveStartMaxRatio: 0.8,
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
  settleAfterChallengeMs: "settle_after_challenge_ms",
  settleAfterFlashMs: "settle_after_flash_ms",
  ovalMinFill: "oval_min_fill",
  ovalHoldMs: "oval_hold_ms",
  moveStartMaxRatio: "move_start_max_ratio",
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
