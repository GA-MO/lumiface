import { describe, expect, it } from "vitest";

import { decode, INPUT_SIZE, letterbox, shortRangeAnchors } from "../src/blazeface.ts";

function raw(entries: { anchor: number; logit: number; cx: number; cy: number; w: number; h: number }[]): Float32Array {
  const out = new Float32Array(896 * 17).fill(-20);
  for (const e of entries) {
    const o = e.anchor * 17;
    out[o] = e.logit;
    out[o + 1] = e.cx;
    out[o + 2] = e.cy;
    out[o + 3] = e.w;
    out[o + 4] = e.h;
  }
  return out;
}

describe("BlazeFace decoding", () => {
  it("lays out 896 anchors: two per cell on 16x16, six per cell on 8x8", () => {
    const a = shortRangeAnchors();
    expect(a.length).toBe(896);
    expect(a[0]).toEqual({ x: 0.5 / 16, y: 0.5 / 16 });
    expect(a[1]).toEqual(a[0]);
    expect(a[2]).toEqual({ x: 1.5 / 16, y: 0.5 / 16 });
    expect(a[512]).toEqual({ x: 0.5 / 8, y: 0.5 / 8 });
    expect(a[517]).toEqual(a[512]);
    expect(a[518]).toEqual({ x: 1.5 / 8, y: 0.5 / 8 });
  });

  it("offsets the box from its anchor in input pixels and undoes the letterbox", () => {
    // Anchor 512 sits at (1/16, 1/16); the box is 32 px wide, centred 4 px right and 2 px down of it.
    const dets = decode(raw([{ anchor: 512, logit: 3, cx: 4, cy: 2, w: 32, h: 32 }]), 0, 0);
    expect(dets.length).toBe(1);
    expect(dets[0].score).toBeCloseTo(0.953, 3);
    expect(dets[0].box.left).toBeCloseTo(1 / 16 + 4 / INPUT_SIZE - 16 / INPUT_SIZE);
    expect(dets[0].box.width).toBeCloseTo(0.25);
    // A 4:3 landscape frame is padded top and bottom by 1/8 of the square each: y stretches back by 4/3.
    const { padX, padY } = letterbox(640, 480);
    expect(padX).toBe(0);
    expect(padY).toBeCloseTo(0.125);
    const boxed = decode(raw([{ anchor: 512, logit: 3, cx: 4, cy: 2, w: 32, h: 32 }]), padX, padY)[0].box;
    expect(boxed.width).toBeCloseTo(0.25);
    expect(boxed.height).toBeCloseTo(0.25 / 0.75);
    expect(boxed.top).toBeCloseTo((1 / 16 + 2 / INPUT_SIZE - 16 / INPUT_SIZE - 0.125) / 0.75);
  });

  it("drops scores under 0.5 and overlapping boxes", () => {
    const dets = decode(
      raw([
        { anchor: 0, logit: -1, cx: 0, cy: 0, w: 32, h: 32 },
        { anchor: 100, logit: 2, cx: 0, cy: 0, w: 40, h: 40 },
        { anchor: 101, logit: 1, cx: 1, cy: 1, w: 40, h: 40 },
        { anchor: 700, logit: 1, cx: 0, cy: 0, w: 40, h: 40 },
      ]),
      0,
      0,
    );
    expect(dets.length).toBe(2);
    expect(dets[0].score).toBeCloseTo(0.881, 3);
    expect(dets[1].box.left).toBeGreaterThan(0.5);
  });
});
