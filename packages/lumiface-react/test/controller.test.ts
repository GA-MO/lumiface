import { afterEach, describe, expect, it } from "vitest";

import { configFromJson, configToJson, DEFAULT_CONFIG } from "../src/config.ts";
import { alignHint, FaceVerifyController, progressOf, visibleRegionFor } from "../src/controller.ts";
import { EN, messageFor, mergeStrings } from "../src/strings.ts";
import { noFace, type Box, type Challenge, type OvalTarget, type VerifyResult } from "../src/types.ts";
import { FakeClient, FakeSource, neutral, pump } from "./fakes.ts";

let src: FakeSource;
let api: FakeClient;
let c: FaceVerifyController;

async function boot(
  challenges: Challenge[],
  o: { response?: VerifyResult; config?: Partial<typeof DEFAULT_CONFIG>; flashColors?: string[]; reference?: boolean; oval?: OvalTarget } = {},
) {
  src = new FakeSource();
  api = new FakeClient(challenges, o.flashColors ?? [], o.oval ?? null);
  if (o.response) api.response = o.response;
  c = new FaceVerifyController({
    source: src,
    recorder: src,
    client: api,
    sessionProvider: () => api.createSession({ reference: o.reference }),
    config: o.config ? { ...DEFAULT_CONFIG, ...o.config } : undefined,
  });
  await c.start();
  await pump();
}

async function emit(s = neutral(0)) {
  src.emit(s);
  await pump();
  await pump();
}

async function align(t: number) {
  await emit(neutral(t));
  await emit(neutral(t + 700));
  expect(c.state.phase).toBe("challenge");
  return t + 700;
}

/** Far, then into the default oval, held for the configured time. */
async function doMove(t: number) {
  await emit(neutral(t, { width: 0.3 }));
  await emit(neutral(t + 300, { width: 0.6 }));
  await emit(neutral(t + 900, { width: 0.6 }));
  return t + 900;
}

afterEach(() => c?.dispose());

describe("alignment follows what the preview shows", () => {
  it("a landscape webcam behind a portrait preview is judged inside the visible crop", () => {
    // 16:9 frame shown in a 0.88 box: only 49% of the width is on screen.
    const region = visibleRegionFor(16 / 9, 0.88);
    expect(region.width).toBeCloseTo(0.495, 2);
    expect(region.left).toBeCloseTo(0.2525, 2);
    // A face 20% of the raw frame fills 40% of the screen: aligned, not "move closer".
    const s = { ...neutral(0), box: { left: 0.4, top: 0.3, width: 0.2, height: 0.45 } };
    expect(alignHint(s, DEFAULT_CONFIG)).toBe("tooFar");
    expect(alignHint(s, DEFAULT_CONFIG, region)).toBeNull();
    // Off to the side of the frame but centred on screen counts as centred.
    const edge = { ...s, box: { ...s.box, left: 0.25 } };
    expect(alignHint(edge, DEFAULT_CONFIG, region)).toBe("notCentered");
    expect(alignHint({ ...s, box: { ...s.box, left: 0.4 } }, DEFAULT_CONFIG, region)).toBeNull();
  });

  it("matching aspects change nothing; a portrait camera in a landscape box crops vertically", () => {
    expect(visibleRegionFor(0.75, 0.75)).toEqual({ left: 0, top: 0, width: 1, height: 1 });
    const r = visibleRegionFor(0.75, 1.5);
    expect(r.width).toBe(1);
    expect(r.height).toBeCloseTo(0.5);
    expect(r.top).toBeCloseTo(0.25);
  });

  it("the controller applies the region it is given", async () => {
    await boot(["face_move"]);
    c.visibleRegion = visibleRegionFor(16 / 9, 0.88);
    const far = { ...neutral(0), box: { left: 0.4, top: 0.3, width: 0.2, height: 0.45 } };
    await emit(far);
    expect(c.state.hint).toBe("holdStill");
  });
});

describe("FaceVerifyController", () => {
  it("face_move: start far, move into the oval, hold; the guide shows the oval", async () => {
    await boot(["face_move"], { oval: { cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35 } });
    c.frameAspect = 0.75;
    const at = (w: number): Box => ({ left: 0.5 - w / 2, top: 0.45 - (w * 1.35 * 0.75) / 2, width: w, height: w * 1.35 * 0.75 });
    await emit({ ...neutral(0), box: at(0.55) });
    expect(c.state.hint).toBe("tooClose");
    await emit({ ...neutral(100), box: at(0.45) });
    await emit({ ...neutral(800), box: at(0.45) });
    expect(c.state.phase).toBe("challenge");
    expect(c.state.challenge).toBe("face_move");
    expect(c.state.target?.width).toBeCloseTo(0.62);
    await emit({ ...neutral(900), box: at(0.45) });
    expect(c.state.hint).toBeNull();
    await emit({ ...neutral(1000), box: { ...at(0.6), left: at(0.6).left + 0.2 } });
    expect(c.state.hint).toBe("notCentered");
    await emit({ ...neutral(1100), box: at(0.6) });
    expect(c.state.hint).toBe("holdStill");
    await emit({ ...neutral(1400), box: at(0.6) });
    await emit({ ...neutral(1700), box: at(0.6) });
    await emit({ ...neutral(2200), box: at(0.6) });
    await pump();
    expect(c.state.phase).toBe("success");
    expect(api.sentEvents.map((e) => e.name)).toEqual(["aligned", "challenge_done"]);
  });

  it("happy path: the recording runs from the plan to the end, events at each boundary, success", async () => {
    await boot(["face_move"]);
    expect(c.state.phase).toBe("aligning");
    expect(c.state.challengeCount).toBe(1);
    expect(api.format).toBe("webm");
    expect(src.recording).toBe(true);
    src.chunk(0);
    let t = await align(1000);
    src.chunk(t);
    expect(c.state.challenge).toBe("face_move");
    t = await doMove(t + 200);
    src.chunk(t);
    await emit(neutral(t + 500, { width: 0.6 }));
    await pump();
    expect(c.state.phase).toBe("success");
    expect(api.sentEvents.map((e) => e.name)).toEqual(["aligned", "challenge_done"]);
    expect(api.sentEvents.map((e) => e.index)).toEqual([undefined, 0]);
    const ts = api.sentEvents.map((e) => e.ts);
    expect(ts[1] - ts[0]).toBeGreaterThanOrEqual(300);
    expect(api.ended).toBe(true);
    // Every chunk the recorder cut while the flow ran went up; the recorder stopped before the verdict.
    expect(api.sentChunks).toEqual([0, 1000 + 700, t]);
    expect(src.recording).toBe(false);
    expect(src.recordings).toBe(1);
    src.chunk(t + 900);
    expect(api.sentChunks.length).toBe(3);
  });

  it("screen flash: a flash event per colour after the challenges, then flash_end", async () => {
    const colors = ["ff0000", "00ff00", "0000ff"];
    await boot(["face_move"], { flashColors: colors });
    let t = await align(0);
    t = await doMove(t + 100);
    await emit(neutral(t + 500));
    expect(c.state.phase).toBe("flash");
    expect(c.state.flashColor).toBe(colors[0]);
    await emit(neutral(t + 700));
    await emit(neutral(t + 1000));
    expect(c.state.flashColor).toBe(colors[1]);
    await emit(neutral(t + 1500));
    expect(c.state.flashColor).toBe(colors[2]);
    await emit(neutral(t + 2000));
    expect(c.state.phase).toBe("challenge");
    expect(c.state.flashColor).toBeNull();
    await emit(neutral(t + 2300));
    expect(c.state.phase).toBe("challenge");
    await emit(neutral(t + 2900));
    await pump();
    expect(c.state.phase).toBe("success");
    expect(api.sentEvents.map((e) => `${e.name}${e.index ?? ""}`)).toEqual(["aligned", "challenge_done0", "flash0", "flash1", "flash2", "flash_end"]);
    expect(api.ended).toBe(true);
  });

  it("alignment hints", async () => {
    await boot(["face_move"]);
    await emit(noFace(0));
    expect(c.state.hint).toBe("noFace");
    await emit({ ...noFace(10), faceCount: 1, box: { left: 0.4, top: 0.4, width: 0.15, height: 0.2 } });
    expect(c.state.hint).toBe("tooFar");
    await emit({ ...noFace(20), faceCount: 1, box: { left: 0, top: 0.3, width: 0.4, height: 0.45 } });
    expect(c.state.hint).toBe("notCentered");
    await emit(neutral(30, { yaw: 40 }));
    expect(c.state.hint).toBe("lookStraight");
    await emit({ ...neutral(40), faceCount: 2 });
    expect(c.state.hint).toBe("multipleFaces");
    await emit(neutral(50));
    expect(c.state.hint).toBe("holdStill");
  });

  it("too close is said while aligning, so the walk starts from where the person held still", async () => {
    await boot(["face_move"]);
    await emit(neutral(0, { width: 0.6 }));
    expect(c.state.phase).toBe("aligning");
    expect(c.state.hint).toBe("tooClose");
    const t = await align(100);
    expect(c.state.hint).toBeNull();
    await emit(neutral(t + 100, { width: 0.6 }));
    expect(c.state.hint).toBe("holdStill");
  });

  it("standing still without the walk does not pass; timeout fails", async () => {
    await boot(["face_move"]);
    const t = await align(0);
    await emit(neutral(t + 1500));
    expect(c.state.phase).toBe("challenge");
    await emit(neutral(t + 11000));
    expect(c.state.result!.reasonCode).toBe("TIMEOUT");
  });

  it("face lost during challenge fails", async () => {
    await boot(["face_move"]);
    const t = await align(0);
    await emit(noFace(t + 500));
    expect(c.state.phase).toBe("challenge");
    await emit(noFace(t + 2300));
    expect(c.state.result!.reasonCode).toBe("FACE_LOST");
  });

  it("server rejection propagates", async () => {
    await boot(["face_move"], { response: { ok: false, mode: "verify", reasonCode: "SPOOF", scores: { match: null, spoof: 0.1, consistency: null }, verificationId: null } });
    let t = await align(0);
    t = await doMove(t + 100);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.phase).toBe("failed");
    expect(c.state.result!.reasonCode).toBe("SPOOF");
  });

  it("neutral_end waits until the face is frontal again (a detector that reports angles)", async () => {
    await boot(["face_move"]);
    let t = await align(0);
    t = await doMove(t + 100);
    await emit(neutral(t + 500, { yaw: 30 }));
    expect(c.state.phase).toBe("challenge");
    expect(c.state.hint).toBe("lookStraight");
    await emit(neutral(t + 600));
    await pump();
    expect(c.state.phase).toBe("success");
  });

  it("uses the session client_config unless a config is given; the session decides liveness", async () => {
    src = new FakeSource();
    api = new FakeClient(["face_move"]);
    api.sessionConfig = { align_hold_ms: 2000 };
    c = new FaceVerifyController({
      source: src,
      recorder: src,
      client: api,
      sessionProvider: () => api.createSession({ reference: false, purpose: "kiosk" }),
    });
    expect(c.flow).toBe("verify");
    await c.start();
    await pump();
    expect(c.flow).toBe("liveness");
    expect(c.config.alignHoldMs).toBe(2000);
    expect(c.state.challengeCount).toBe(1);
    expect(api.lastReference).toBe(false);
    expect(api.lastPurpose).toBe("kiosk");
    await emit(neutral(0));
    await emit(neutral(700));
    expect(c.state.phase).toBe("aligning");
    expect(progressOf(c.state)).toBe(0);
    await emit(neutral(2100));
    expect(c.state.phase).toBe("challenge");
  });

  it("cancel", async () => {
    await boot(["face_move"]);
    c.cancel();
    expect(c.state.result!.reasonCode).toBe("CANCELLED");
  });

  it("a stream the server refuses ends the flow with the server's reason code", async () => {
    src = new FakeSource();
    api = new FakeClient(["face_move"]);
    api.planError = "SESSION_USED";
    c = new FaceVerifyController({ source: src, recorder: src, client: api, sessionProvider: () => api.createSession() });
    await c.start();
    await pump();
    expect(c.state.phase).toBe("failed");
    expect(c.state.result!.reasonCode).toBe("SESSION_USED");
    expect(c.state.result!.sessionId).toBe("s1");
  });

  it("cancelling mid-flow closes the stream and stops the recorder", async () => {
    await boot(["face_move"]);
    await emit(neutral(0));
    expect(src.recording).toBe(true);
    c.cancel();
    expect(api.closed).toBe(true);
    expect(api.ended).toBe(false);
    expect(src.recording).toBe(false);
  });

  it("a failing session provider ends the flow with NETWORK_ERROR", async () => {
    src = new FakeSource();
    api = new FakeClient(["face_move"]);
    c = new FaceVerifyController({
      source: src,
      recorder: src,
      client: api,
      sessionProvider: async () => {
        throw new Error("backend down");
      },
    });
    await c.start();
    await pump();
    expect(c.state.phase).toBe("failed");
    expect(c.state.result!.reasonCode).toBe("NETWORK_ERROR");
  });
});

describe("config and strings", () => {
  it("config json round-trips and keeps defaults", () => {
    const json = configToJson({ ...DEFAULT_CONFIG, ovalHoldMs: 900 });
    expect(Object.keys(json).length).toBe(13);
    expect(configFromJson(json).ovalHoldMs).toBe(900);
    expect(configFromJson({ move_start_max_ratio: 0.5 }).moveStartMaxRatio).toBe(0.5);
    expect(configFromJson(null).ovalHoldMs).toBe(DEFAULT_CONFIG.ovalHoldMs);
  });

  it("messages follow the flow and mergeStrings keeps nested maps", () => {
    const done = { ...c?.state, phase: "success" as const, hint: null, challenge: null, challengeIndex: 0, challengeCount: 0, flashColor: null, flashIndex: 0, result: null };
    expect(messageFor(EN, done, "verify")).toBe("Verified");
    expect(messageFor(EN, done, "liveness")).toBe("Live person confirmed");
    const custom = mergeStrings(EN, { success: "Door open", reasons: { NO_MATCH: "Nope" } });
    expect(messageFor(custom, done, "verify")).toBe("Door open");
    expect(custom.reasons.NO_MATCH).toBe("Nope");
    expect(custom.reasons.SPOOF).toBe(EN.reasons.SPOOF);
  });
});

describe("alignment bounds on a landscape webcam", () => {
  it("a full-width landscape preview keeps a band to stand in: the lower bound shrinks with the oval's start", async () => {
    await boot(["face_move"], { oval: { cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35 } });
    c.frameAspect = 16 / 9;
    c.visibleRegion = visibleRegionFor(16 / 9, 16 / 9);
    // The oval is 0.349 of the frame width, its start 0.279: below min_face_width_fraction (0.28), which used to
    // leave nothing between "move closer" and "move back". The band is now [0.163, 0.279].
    const box = (w: number): Box => ({ left: 0.5 - w / 2, top: 0.2, width: w, height: 0.5 });
    await emit({ ...neutral(0), box: box(0.3) });
    expect(c.state.hint).toBe("tooClose");
    await emit({ ...neutral(100), box: box(0.12) });
    expect(c.state.hint).toBe("tooFar");
    await emit({ ...neutral(200), box: box(0.22) });
    expect(c.state.hint).toBe("holdStill");
    await emit({ ...neutral(900), box: box(0.22) });
    expect(c.state.phase).toBe("challenge");
  });

  it("the oval's start width, in the visible region, caps the aligned face so the walk begins from the hold", async () => {
    await boot(["face_move"], { oval: { cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35 } });
    c.frameAspect = 16 / 9;
    c.visibleRegion = visibleRegionFor(16 / 9, 0.88);
    // The oval is 0.62 of the short side: 0.349 of the frame width, 0.705 of the visible region.
    // Its start (0.8 of that) is 0.564 of the region: wider than max_face_width_fraction would allow,
    // so a face at 0.45 of the region (0.223 of the frame) is a valid start.
    const box = (w: number): Box => ({ left: 0.5 - w / 2, top: 0.2, width: w, height: 0.5 });
    await emit({ ...neutral(0), box: box(0.3) });
    expect(c.state.hint).toBe("tooClose");
    await emit({ ...neutral(100), box: box(0.223) });
    expect(c.state.hint).toBe("holdStill");
    await emit({ ...neutral(800), box: box(0.223) });
    expect(c.state.phase).toBe("challenge");
    await emit({ ...neutral(900), box: box(0.223) });
    expect(c.state.hint).toBeNull();
  });
});
