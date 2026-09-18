import { LumifaceError, type FaceSession, type StreamPlan, type Subject, type VerifyResult } from "./types.ts";

export function reasonCode(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && typeof (detail as { reason_code?: unknown }).reason_code === "string") {
    return (detail as { reason_code: string }).reason_code;
  }
  return `HTTP_${status}`;
}

export function toScores(j: Record<string, unknown> | undefined) {
  return {
    match: (j?.match as number | null | undefined) ?? null,
    spoof: (j?.spoof as number | null | undefined) ?? null,
    consistency: (j?.consistency as number | null | undefined) ?? null,
  };
}

export function toSubject(j: Record<string, unknown>): Subject {
  return {
    externalId: j.external_id as string,
    name: (j.name as string) ?? "",
    enrollSpoofScore: j.enroll_spoof_score as number,
    expiresAt: (j.expires_at as string | null | undefined) ?? null,
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

export function planFromJson(j: Record<string, unknown>): StreamPlan {
  return {
    challenges: (j.challenges as StreamPlan["challenges"]) ?? [],
    flashColors: (j.flash_colors as string[]) ?? [],
    flashHoldMs: (j.flash_hold_ms as number) ?? 450,
    clientConfig: (j.client_config as Record<string, unknown>) ?? null,
  };
}

export class Http {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl: string, fetchImpl: typeof fetch | undefined) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetchImpl = fetchImpl ?? fetch.bind(globalThis);
  }

  async request(path: string, init: RequestInit = {}, bearer?: string): Promise<{ status: number; body: unknown }> {
    const headers = new Headers(init.headers);
    if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
    const text = await res.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = text;
    }
    return { status: res.status, body };
  }

}
