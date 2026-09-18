import { afterEach, describe, expect, it } from "vitest";

import { configFromJson, configToJson, DEFAULT_CONFIG } from "../src/config.ts";
import { FaceEnrollController, FaceVerifyController, progressOf } from "../src/controller.ts";
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
    subjectId: o.subjectId === undefined ? "E001" : o.subjectId,
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

describe("FaceVerifyController", () => {
  it("happy path: blink + smile -> 4 frames uploaded, success", async () => {
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
    expect(api.sentFrames!.map((f) => f.kind)).toEqual(["neutral_start", "challenge_0", "challenge_1", "neutral_end"]);
    expect(api.sentDurations!.length).toBe(2);
    expect(api.sentDurations!.every((d) => d >= 300)).toBe(true);
    expect(src.captures).toBe(4);
  });

  it("screen flash: one frame per colour after the challenges, before neutral_end", async () => {
    const colors = ["ff0000", "00ff00", "0000ff"];
    await boot(["turn_left"], { flashColors: colors });
    let t = await align(0);
    t = await doTurn(t + 100);
    await emit(neutral(t + 500));
    expect(c.state.phase).toBe("flash");
    expect(c.state.flashColor).toBe(colors[0]);
    await emit(neutral(t + 700));
    expect(src.captures).toBe(2);
    await emit(neutral(t + 1000));
    expect(src.captures).toBe(3);
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
    expect(api.sentFrames!.map((f) => f.kind)).toEqual(["neutral_start", "challenge_0", "flash_0", "flash_1", "flash_2", "neutral_end"]);
    expect(api.sentDurations!.length).toBe(1);
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
    expect(api.sentFrames!.length).toBe(4);
    expect(api.sentDurations!.length).toBe(2);
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

  it("uses the session client_config unless a config is given; liveness sends no subject", async () => {
    src = new FakeSource();
    api = new FakeClient(["blink"]);
    api.sessionConfig = { align_hold_ms: 2000, parallax_when_no_turn: false };
    c = new FaceVerifyController({ source: src, capturer: src, client: api, purpose: "kiosk" });
    expect(c.flow).toBe("liveness");
    await c.start();
    await pump();
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
});

describe("FaceEnrollController", () => {
  it("aligns, captures one frame and enrols", async () => {
    const s = new FakeSource();
    const client = new FakeClient([]);
    const e = new FaceEnrollController({ source: s, capturer: s, client, externalId: "E9", name: "Nine" });
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
    const e = new FaceEnrollController({ source: s, capturer: s, client: new FakeClient([]), externalId: "REJECT" });
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
