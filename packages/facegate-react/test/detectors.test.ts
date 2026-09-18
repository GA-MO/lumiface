import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "../src/config.ts";
import { BlinkDetector, NodDetector, SmileDetector, TurnDetector } from "../src/detectors.ts";
import { neutral } from "./fakes.ts";

const cfg = DEFAULT_CONFIG;

describe("BlinkDetector", () => {
  it("open -> closed 120ms -> open succeeds", () => {
    const d = new BlinkDetector(cfg);
    expect(d.feed(neutral(0))).toBe(false);
    expect(d.feed(neutral(100, { eye: 0.1 }))).toBe(false);
    expect(d.feed(neutral(220, { eye: 0.9 }))).toBe(true);
  });

  it("eyes closed too long resets", () => {
    const d = new BlinkDetector(cfg);
    d.feed(neutral(0));
    d.feed(neutral(100, { eye: 0.1 }));
    expect(d.feed(neutral(900, { eye: 0.1 }))).toBe(false);
    expect(d.feed(neutral(950, { eye: 0.9 }))).toBe(false);
    d.feed(neutral(1000));
    d.feed(neutral(1100, { eye: 0.1 }));
    expect(d.feed(neutral(1200, { eye: 0.9 }))).toBe(true);
  });
});

describe("SmileDetector", () => {
  it("requires a non-smiling baseline then a hold", () => {
    const d = new SmileDetector(cfg);
    expect(d.feed(neutral(0, { smile: 0.9 }))).toBe(false);
    expect(d.feed(neutral(100, { smile: 0.1 }))).toBe(false);
    expect(d.feed(neutral(200, { smile: 0.9 }))).toBe(false);
    expect(d.feed(neutral(520, { smile: 0.9 }))).toBe(true);
  });
});

describe("TurnDetector", () => {
  it("left needs positive yaw beyond threshold, held", () => {
    const d = new TurnDetector(cfg, true);
    expect(d.feed(neutral(0, { yaw: 10 }))).toBe(false);
    expect(d.feed(neutral(100, { yaw: -40 }))).toBe(false);
    expect(d.feed(neutral(200, { yaw: 30 }))).toBe(false);
    expect(d.feed(neutral(450, { yaw: 30 }))).toBe(true);
  });

  it("rotated flat picture never passes", () => {
    const d = new TurnDetector(cfg, true);
    expect(d.feed(neutral(0, { flat: true }))).toBe(false);
    expect(d.feed(neutral(100, { yaw: 30, flat: true }))).toBe(false);
    expect(d.feed(neutral(2000, { yaw: 40, flat: true }))).toBe(false);
  });

  it("needs a frontal baseline before the turn", () => {
    const d = new TurnDetector(cfg, true);
    expect(d.feed(neutral(0, { yaw: 30 }))).toBe(false);
    expect(d.feed(neutral(300, { yaw: 30 }))).toBe(false);
    d.feed(neutral(400));
    d.feed(neutral(500, { yaw: 30 }));
    expect(d.feed(neutral(800, { yaw: 30 }))).toBe(true);
  });
});

describe("NodDetector", () => {
  it("either pitch direction held passes", () => {
    const d = new NodDetector(cfg);
    d.feed(neutral(0));
    d.feed(neutral(100, { pitch: -20 }));
    expect(d.feed(neutral(350, { pitch: -20 }))).toBe(true);
  });
});
