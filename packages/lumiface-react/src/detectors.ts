import type { LivenessConfig } from "./config.ts";
import type { Box, Challenge, FaceSignal } from "./types.ts";

/** Fed with signals, returns true once the challenge is satisfied. Single use. */
export interface ChallengeDetector {
  feed(s: FaceSignal): boolean;
}

export type MoveHint = "tooClose" | "notCentered" | "holdStill" | null;

/** Start far (face narrower than `moveStartMaxRatio` of the oval), move closer until the face box is
 *  `ovalMinFill` of the oval's width and centred within a fifth of it, hold for `ovalHoldMs`. `oval` and
 *  the boxes are in frame-normalised coordinates. `hint` is what the person should do next; null while
 *  approaching, when the challenge text itself is the instruction. */
export class FaceMoveDetector implements ChallengeDetector {
  private startedFar = false;
  private fittedSince: number | null = null;
  hint: MoveHint = null;

  constructor(
    private readonly config: LivenessConfig,
    readonly oval: Box,
  ) {}

  feed(s: FaceSignal): boolean {
    const b = s.box;
    if (!b) return false;
    const o = this.oval;
    if (!this.startedFar) {
      if (b.width > o.width * this.config.moveStartMaxRatio) {
        this.hint = "tooClose";
        return false;
      }
      this.startedFar = true;
    }
    const filled = b.width >= o.width * this.config.ovalMinFill;
    const offCentre =
      Math.abs(b.left + b.width / 2 - (o.left + o.width / 2)) > o.width * 0.2 ||
      Math.abs(b.top + b.height / 2 - (o.top + o.height / 2)) > o.height * 0.2;
    if (filled && !offCentre) {
      this.hint = "holdStill";
      this.fittedSince ??= s.tsMs;
      return s.tsMs - this.fittedSince >= this.config.ovalHoldMs;
    }
    this.fittedSince = null;
    this.hint = filled && offCentre ? "notCentered" : null;
    return false;
  }
}

export const DEFAULT_OVAL: Box = { left: 0.19, top: 0.2, width: 0.62, height: 0.5 };

export function detectorFor(challenge: Challenge, config: LivenessConfig, oval?: Box): ChallengeDetector {
  switch (challenge) {
    case "face_move":
      return new FaceMoveDetector(config, oval ?? DEFAULT_OVAL);
  }
}
