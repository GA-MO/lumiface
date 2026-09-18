import { afterEach, describe, expect, it } from "vitest";

import { configFromJson, configToJson, DEFAULT_CONFIG } from "../src/config.ts";
import { alignHint, FaceEnrollController, FaceVerifyController, progressOf, visibleRegionFor } from "../src/controller.ts";
import { EN, messageFor, mergeStrings } from "../src/strings.ts";
import { noFace, type Challenge, type VerifyResult } from "../src/types.ts";
import { FakeClient, FakeSource, neutral, pump } from "./fakes.ts";

let src: FakeSource;
let api: FakeClient;
let c: FaceVerifyController;

async function boot(challenges: Challenge[], o: { response?: VerifyResult; config?: Partial<typeof DEFAULT_CONFIG>; flashColors?: string[]; subjectId?: string | null } = {}) {
  src = new FakeSource();
  api = new FakeClient(challenges, o.flashColors ?? []);
  if (o.response) api.response = o.response;
  c = new FaceVerifyController({
    source: src,
    capturer: src,
    client: api,
    sessionProvider: () => api.createSession({ subjectId: o.subjectId === undefined ? "E001" : o.subjectId }),
    config: o.config ? { ...DEFAULT_CONFIG, ...o.config } : undefined,
    random: () => 0.9,
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

async function doBlink(t: number) {
  await emit(neutral(t));
  await emit(neutral(t + 100, { eye: 0.1 }));
  await emit(neutral(t + 250, { eye: 0.95 }));
  return t + 250;
}

async function doSmile(t: number) {
  await emit(neutral(t, { smile: 0.1 }));
  await emit(neutral(t + 100, { smile: 0.9 }));
  await emit(neutral(t + 500, { smile: 0.9 }));
  return t + 500;
}

async function doTurn(t: number) {
  const yaw = c.state.challenge === "turn_left" ? 30 : -30;
  await emit(neutral(t));
  await emit(neutral(t + 100, { yaw }));
  await emit(neutral(t + 400, { yaw }));
  return t + 400;
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
    await boot(["blink"], { config: { parallaxWhenNoTurn: false } });
    c.visibleRegion = visibleRegionFor(16 / 9, 0.88);
    const far = { ...neutral(0), box: { left: 0.4, top: 0.3, width: 0.2, height: 0.45 } };
    await emit(far);
    expect(c.state.hint).toBe("holdStill");
  });
});

describe("FaceVerifyController", () => {
  it("happy path: blink + smile -> frames streamed throughout, events at each boundary, success", async () => {
    await boot(["blink", "smile"], { config: { parallaxWhenNoTurn: false } });
    expect(c.state.phase).toBe("aligning");
    expect(c.state.challengeCount).toBe(2);
    let t = await align(1000);
    expect(c.state.challenge).toBe("blink");
    t = await doBlink(t + 200);
    await emit(neutral(t + 500));
    expect(c.state.challenge).toBe("smile");
    expect(c.state.challengeIndex).toBe(1);
    t = await doSmile(t + 600);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.phase).toBe("success");
    expect(api.sentEvents.map((e) => e.name)).toEqual(["aligned", "challenge_done", "challenge_done"]);
    expect(api.sentEvents.map((e) => e.index)).toEqual([undefined, 0, 1]);
    const ts = api.sentEvents.map((e) => e.ts);
    expect(ts[1] - ts[0]).toBeGreaterThanOrEqual(300);
    expect(api.ended).toBe(true);
    // Frames went up the whole time, throttled to the stream rate, not just at the boundaries.
    expect(src.captures).toBe(api.sentFrames.length);
    expect(api.sentFrames.length).toBeGreaterThan(4);
    expect(api.sentFrames[0]).toBeLessThan(ts[0]);
    expect(api.sentFrames[api.sentFrames.length - 1]).toBeGreaterThan(ts[2]);
  });

  it("screen flash: a flash event per colour after the challenges, then flash_end", async () => {
    const colors = ["ff0000", "00ff00", "0000ff"];
    await boot(["turn_left"], { flashColors: colors });
    let t = await align(0);
    t = await doTurn(t + 100);
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

  it("no turn from server -> client-only turn appended, flat picture never passes it", async () => {
    await boot(["blink", "smile"]);
    expect(c.state.challengeCount).toBe(3);
    let t = await align(1000);
    t = await doBlink(t + 200);
    await emit(neutral(t + 500));
    t = await doSmile(t + 600);
    await emit(neutral(t + 500));
    expect(c.state.challengeIndex).toBe(2);
    expect(c.state.challenge).toBe("turn_right");
    await emit(neutral(t + 600, { yaw: -30, flat: true }));
    await emit(neutral(t + 1200, { yaw: -30, flat: true }));
    expect(c.state.phase).toBe("challenge");
    t = await doTurn(t + 1300);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.phase).toBe("success");
    // The client-only turn is not reported to the server.
    expect(api.sentEvents.map((e) => e.name)).toEqual(["aligned", "challenge_done", "challenge_done"]);
  });

  it("alignment hints", async () => {
    await boot(["blink"]);
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

  it("slow blink does not pass; timeout fails", async () => {
    await boot(["blink"]);
    const t = await align(0);
    await emit(neutral(t + 100));
    await emit(neutral(t + 200, { eye: 0.1 }));
    await emit(neutral(t + 1500, { eye: 0.1 }));
    await emit(neutral(t + 1600, { eye: 0.9 }));
    expect(c.state.phase).toBe("challenge");
    await emit(neutral(t + 11000));
    expect(c.state.result!.reasonCode).toBe("TIMEOUT");
  });

  it("face lost during challenge fails", async () => {
    await boot(["turn_left"]);
    const t = await align(0);
    await emit(noFace(t + 500));
    expect(c.state.phase).toBe("challenge");
    await emit(noFace(t + 2300));
    expect(c.state.result!.reasonCode).toBe("FACE_LOST");
  });

  it("server rejection propagates", async () => {
    await boot(["blink"], { response: { ok: false, mode: "verify", reasonCode: "SPOOF", scores: { match: null, spoof: 0.1, consistency: null }, verificationId: null }, config: { parallaxWhenNoTurn: false } });
    let t = await align(0);
    t = await doBlink(t + 100);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.phase).toBe("failed");
    expect(c.state.result!.reasonCode).toBe("SPOOF");
  });

  it("neutral_end waits until the face is frontal again", async () => {
    await boot(["turn_left"]);
    const t = await align(0);
    await emit(neutral(t + 100, { yaw: 30 }));
    await emit(neutral(t + 400, { yaw: 30 }));
    await emit(neutral(t + 900, { yaw: 30 }));
    expect(c.state.phase).toBe("challenge");
    expect(c.state.hint).toBe("lookStraight");
    await emit(neutral(t + 1000));
    await pump();
    expect(c.state.phase).toBe("success");
  });

  it("uses the session client_config unless a config is given; the session decides liveness", async () => {
    src = new FakeSource();
    api = new FakeClient(["blink"]);
    api.sessionConfig = { align_hold_ms: 2000, parallax_when_no_turn: false };
    c = new FaceVerifyController({
      source: src,
      capturer: src,
      client: api,
      sessionProvider: () => api.createSession({ subjectId: null, purpose: "kiosk" }),
    });
    expect(c.flow).toBe("verify");
    await c.start();
    await pump();
    expect(c.flow).toBe("liveness");
    expect(c.config.alignHoldMs).toBe(2000);
    expect(c.state.challengeCount).toBe(1);
    expect(api.lastSubjectId).toBeNull();
    expect(api.lastPurpose).toBe("kiosk");
    await emit(neutral(0));
    await emit(neutral(700));
    expect(c.state.phase).toBe("aligning");
    expect(progressOf(c.state)).toBe(0);
    await emit(neutral(2100));
    expect(c.state.phase).toBe("challenge");
  });

  it("cancel", async () => {
    await boot(["blink"]);
    c.cancel();
    expect(c.state.result!.reasonCode).toBe("CANCELLED");
  });

  it("a stream the server refuses ends the flow with the server's reason code", async () => {
    src = new FakeSource();
    api = new FakeClient(["blink"]);
    api.planError = "SESSION_USED";
    c = new FaceVerifyController({ source: src, capturer: src, client: api, sessionProvider: () => api.createSession() });
    await c.start();
    await pump();
    expect(c.state.phase).toBe("failed");
    expect(c.state.result!.reasonCode).toBe("SESSION_USED");
    expect(c.state.result!.sessionId).toBe("s1");
  });

  it("cancelling mid-flow closes the stream", async () => {
    await boot(["blink"]);
    await emit(neutral(0));
    c.cancel();
    expect(api.closed).toBe(true);
    expect(api.ended).toBe(false);
  });

  it("a failing session provider ends the flow with NETWORK_ERROR", async () => {
    src = new FakeSource();
    api = new FakeClient(["blink"]);
    c = new FaceVerifyController({
      source: src,
      capturer: src,
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

describe("FaceEnrollController", () => {
  it("aligns, captures one frame and enrols", async () => {
    const s = new FakeSource();
    const client = new FakeClient([]);
    const e = new FaceEnrollController({ source: s, capturer: s, client, enrolTokenProvider: async () => "tok:E9:Nine" });
    await e.start();
    s.emit(noFace(0));
    expect(e.state.hint).toBe("noFace");
    s.emit(neutral(100));
    s.emit(neutral(800));
    await pump();
    await pump();
    expect(e.state.phase).toBe("success");
    expect(e.state.result!.subject!.externalId).toBe("E9");
    expect(s.captures).toBe(1);
    e.dispose();
  });

  it("server rejection becomes a failed result with the reason code", async () => {
    const s = new FakeSource();
    const e = new FaceEnrollController({ source: s, capturer: s, client: new FakeClient([]), enrolTokenProvider: async () => "tok:REJECT" });
    await e.start();
    s.emit(neutral(0));
    s.emit(neutral(700));
    await pump();
    await pump();
    expect(e.state.phase).toBe("failed");
    expect(e.state.result!.reasonCode).toBe("POSE_NOT_FRONTAL");
    e.dispose();
  });
});

describe("config and strings", () => {
  it("config json round-trips and keeps defaults", () => {
    const json = configToJson({ ...DEFAULT_CONFIG, blinkMaxMs: 900 });
    expect(Object.keys(json).length).toBe(23);
    expect(configFromJson(json).blinkMaxMs).toBe(900);
    expect(configFromJson({ smile_hold_ms: 100 }).smileHoldMs).toBe(100);
    expect(configFromJson(null).smileHoldMs).toBe(DEFAULT_CONFIG.smileHoldMs);
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
