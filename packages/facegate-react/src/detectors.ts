import type { LivenessConfig } from "./config.ts";
import { eyeOpen, noseParallax, type Challenge, type FaceSignal } from "./types.ts";

/** Fed with signals, returns true once the challenge is satisfied. Single use. */
export interface ChallengeDetector {
  feed(s: FaceSignal): boolean;
}

/** open -> closed (blinkMinMs..blinkMaxMs) -> open. Closed too long resets. */
export class BlinkDetector implements ChallengeDetector {
  private seenOpen = false;
  private closedAt: number | null = null;

  constructor(private readonly config: LivenessConfig) {}

  feed(s: FaceSignal): boolean {
    const e = eyeOpen(s);
    if (e === null) return false;
    if (this.closedAt === null) {
      if (e >= this.config.eyeOpenThreshold) this.seenOpen = true;
      if (this.seenOpen && e <= this.config.eyeClosedThreshold) this.closedAt = s.tsMs;
      return false;
    }
    const closedFor = s.tsMs - this.closedAt;
    if (closedFor > this.config.blinkMaxMs) {
      this.closedAt = null;
      this.seenOpen = false;
      return false;
    }
    if (e >= this.config.eyeOpenThreshold) {
      if (closedFor >= this.config.blinkMinMs) return true;
      this.closedAt = null;
    }
    return false;
  }
}

/** Non-smiling baseline first, then smile >= threshold held for smileHoldMs. */
export class SmileDetector implements ChallengeDetector {
  private baseline = false;
  private smilingSince: number | null = null;

  constructor(private readonly config: LivenessConfig) {}

  feed(s: FaceSignal): boolean {
    const v = s.smile;
    if (v === null) return false;
    if (!this.baseline) {
      if (v <= this.config.smileBaselineMax) this.baseline = true;
      return false;
    }
    if (v >= this.config.smileThreshold) {
      this.smilingSince ??= s.tsMs;
      return s.tsMs - this.smilingSince >= this.config.smileHoldMs;
    }
    this.smilingSince = null;
    return false;
  }
}

/**
 * Yaw beyond turnMinYaw in the requested direction held for turnHoldMs, and
 * (parallaxMinShift > 0) the nose must have moved relative to the eyes since
 * the frontal baseline, which a rotated flat picture cannot do.
 */
export class TurnDetector implements ChallengeDetector {
  private since: number | null = null;
  private baseline: number | null = null;

  constructor(
    private readonly config: LivenessConfig,
    private readonly left: boolean,
  ) {}

  private get needParallax() {
    return this.config.parallaxMinShift > 0;
  }

  feed(s: FaceSignal): boolean {
    const yaw = s.yaw;
    if (yaw === null) return false;
    if (this.needParallax && Math.abs(yaw) <= this.config.neutralMaxYaw) {
      this.baseline = noseParallax(s) ?? this.baseline;
    }
    const dirOk = this.left ? yaw >= this.config.turnMinYaw : yaw <= -this.config.turnMinYaw;
    if (!dirOk) {
      this.since = null;
      return false;
    }
    if (this.needParallax) {
      const p = noseParallax(s);
      if (this.baseline === null || p === null || Math.abs(p - this.baseline) < this.config.parallaxMinShift) {
        this.since = null;
        return false;
      }
    }
    this.since ??= s.tsMs;
    return s.tsMs - this.since >= this.config.turnHoldMs;
  }
}

/** |pitch| beyond nodMinPitch held for nodHoldMs. */
export class NodDetector implements ChallengeDetector {
  private since: number | null = null;

  constructor(private readonly config: LivenessConfig) {}

  feed(s: FaceSignal): boolean {
    const p = s.pitch;
    if (p === null) return false;
    if (Math.abs(p) < this.config.nodMinPitch) {
      this.since = null;
      return false;
    }
    this.since ??= s.tsMs;
    return s.tsMs - this.since >= this.config.nodHoldMs;
  }
}

export function detectorFor(challenge: Challenge, config: LivenessConfig): ChallengeDetector {
  switch (challenge) {
    case "blink":
      return new BlinkDetector(config);
    case "smile":
      return new SmileDetector(config);
    case "turn_left":
      return new TurnDetector(config, true);
    case "turn_right":
      return new TurnDetector(config, false);
    case "nod":
      return new NodDetector(config);
  }
}
