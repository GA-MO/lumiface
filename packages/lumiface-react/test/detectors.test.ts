import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "../src/config.ts";
import { DEFAULT_OVAL, detectorFor, FaceMoveDetector } from "../src/detectors.ts";
import { neutral } from "./fakes.ts";

const cfg = DEFAULT_CONFIG;

describe("FaceMoveDetector", () => {
  it("must start far, then fill the oval centred and hold", () => {
    const d = new FaceMoveDetector(cfg, DEFAULT_OVAL);
    expect(d.feed(neutral(0, { width: 0.5 }))).toBe(false);
    expect(d.hint).toBe("tooClose");
    expect(d.feed(neutral(100, { width: 0.3 }))).toBe(false);
    expect(d.hint).toBeNull();
    const off = neutral(200, { width: 0.6 });
    expect(d.feed({ ...off, box: { ...off.box!, left: off.box!.left + 0.2 } })).toBe(false);
    expect(d.hint).toBe("notCentered");
    expect(d.feed(neutral(300, { width: 0.6 }))).toBe(false);
    expect(d.hint).toBe("holdStill");
    expect(d.feed(neutral(600, { width: 0.6 }))).toBe(false);
    expect(d.feed(neutral(850, { width: 0.6 }))).toBe(true);
  });

  it("leaving the oval restarts the hold", () => {
    const d = new FaceMoveDetector(cfg, DEFAULT_OVAL);
    d.feed(neutral(0, { width: 0.3 }));
    d.feed(neutral(100, { width: 0.6 }));
    d.feed(neutral(400, { width: 0.4 }));
    expect(d.feed(neutral(700, { width: 0.6 }))).toBe(false);
    expect(d.feed(neutral(1250, { width: 0.6 }))).toBe(true);
  });

  it("a face that was never far does not pass by standing close", () => {
    const d = new FaceMoveDetector(cfg, DEFAULT_OVAL);
    expect(d.feed(neutral(0, { width: 0.6 }))).toBe(false);
    expect(d.feed(neutral(2000, { width: 0.6 }))).toBe(false);
    expect(d.hint).toBe("tooClose");
  });

  it("no face feeds nothing", () => {
    const d = detectorFor("face_move", cfg);
    expect(d.feed({ ...neutral(0), box: null, faceCount: 0 })).toBe(false);
  });
});
