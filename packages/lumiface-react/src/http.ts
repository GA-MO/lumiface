import type { FaceSession, OvalTarget, StreamPlan, VerifyResult } from "./types.ts";

export function toScores(j: Record<string, unknown> | undefined) {
  return {
    match: (j?.match as number | null | undefined) ?? null,
    spoof: (j?.spoof as number | null | undefined) ?? null,
    consistency: (j?.consistency as number | null | undefined) ?? null,
  };
}

export function toVerifyResult(j: Record<string, unknown>): VerifyResult {
  return {
    ok: j.ok as boolean,
    mode: (j.mode as string) ?? "verify",
    reasonCode: j.reason_code as string,
    scores: toScores(j.scores as Record<string, unknown>),
    verificationId: (j.verification_id as number | null) ?? null,
  };
}

/** Parses the server's `POST /v1/sessions` JSON, e.g. one your backend proxied to the browser. */
export function sessionFromJson(j: Record<string, unknown>): FaceSession {
  return {
    id: j.session_id as string,
    token: (j.session_token as string) ?? "",
    mode: ((j.mode as string) ?? "verify") as FaceSession["mode"],
    purpose: (j.purpose as string) ?? "",
    ttlSeconds: j.ttl_seconds as number,
    clientConfig: (j.client_config as Record<string, unknown>) ?? null,
  };
}

function ovalFromJson(o: unknown): OvalTarget | null {
  if (!o || typeof o !== "object") return null;
  const j = o as Record<string, unknown>;
  return {
    cx: (j.cx as number) ?? 0.5,
    cy: (j.cy as number) ?? 0.45,
    width: (j.width as number) ?? 0.62,
    heightRatio: (j.height_ratio as number) ?? 1.35,
  };
}

export function planFromJson(j: Record<string, unknown>): StreamPlan {
  return {
    challenges: (j.challenges as StreamPlan["challenges"]) ?? [],
    flashColors: (j.flash_colors as string[]) ?? [],
    flashHoldMs: (j.flash_hold_ms as number) ?? 450,
    clientConfig: (j.client_config as Record<string, unknown>) ?? null,
    oval: ovalFromJson(j.oval),
  };
}
