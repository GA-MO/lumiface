import {
  LumifaceError,
  type CapturedFrame,
  type FaceSession,
  type PolicyPreset,
  type ProjectPolicy,
  type Subject,
  type VerificationRecord,
  type VerifyResult,
} from "./types.ts";

export interface LumifaceClientOptions {
  baseUrl: string;
  /**
   * The project secret. Only for development or trusted (server-side) code: in the browser
   * anyone can read it and manage every subject and the policy. Production apps omit it and
   * hold a session token or an enrol token issued by their own backend instead.
   */
  apiKey?: string;
  fetch?: typeof fetch;
}

function reasonCode(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && typeof (detail as { reason_code?: unknown }).reason_code === "string") {
    return (detail as { reason_code: string }).reason_code;
  }
  return `HTTP_${status}`;
}

function toScores(j: Record<string, unknown> | undefined) {
  return {
    match: (j?.match as number | null | undefined) ?? null,
    spoof: (j?.spoof as number | null | undefined) ?? null,
    consistency: (j?.consistency as number | null | undefined) ?? null,
  };
}

function toSubject(j: Record<string, unknown>): Subject {
  return {
    externalId: j.external_id as string,
    name: (j.name as string) ?? "",
    enrollSpoofScore: j.enroll_spoof_score as number,
    expiresAt: (j.expires_at as string | null | undefined) ?? null,
  };
}

/** Parses the server's `POST /v1/sessions` JSON, e.g. one your backend proxied to the browser. */
export function sessionFromJson(j: Record<string, unknown>): FaceSession {
  return {
    id: j.session_id as string,
    token: (j.session_token as string) ?? "",
    mode: ((j.mode as string) ?? "verify") as FaceSession["mode"],
    purpose: (j.purpose as string) ?? "",
    challenges: j.challenges as FaceSession["challenges"],
    frameKinds: j.frame_kinds as string[],
    ttlSeconds: j.ttl_seconds as number,
    flashColors: (j.flash_colors as string[]) ?? [],
    flashHoldMs: (j.flash_hold_ms as number) ?? 450,
    clientConfig: (j.client_config as Record<string, unknown>) ?? null,
  };
}

/**
 * Thin client for the Lumiface server. In production the browser holds no project key: the
 * backend creates the session or enrol token and the client authenticates each call with it.
 */
export class LumifaceClient {
  private readonly baseUrl: string;
  private readonly apiKey: string | undefined;
  private readonly fetchImpl: typeof fetch;

  constructor(options: LumifaceClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.fetchImpl = options.fetch ?? fetch.bind(globalThis);
  }

  private async request(
    path: string,
    init: RequestInit = {},
    bearer?: string | null,
  ): Promise<{ status: number; body: unknown }> {
    const headers = new Headers(init.headers);
    if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
    else if (this.apiKey) headers.set("X-API-Key", this.apiKey);
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

  private async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const { status, body } = await this.request(path, init);
    if (status >= 400) throw new LumifaceError(reasonCode(body, status), body);
    return body as T;
  }

  private jsonInit(method: string, data: unknown): RequestInit {
    return { method, body: JSON.stringify(data), headers: { "Content-Type": "application/json" } };
  }

  async createSession(options: { subjectId?: string | null; purpose?: string } = {}): Promise<FaceSession> {
    const j = await this.json<Record<string, unknown>>(
      "/v1/sessions",
      this.jsonInit("POST", { subject_id: options.subjectId ?? null, purpose: options.purpose ?? "" }),
    );
    return sessionFromJson(j);
  }

  async verify(options: {
    sessionId: string;
    frames: CapturedFrame[];
    challengeDurationsMs: number[];
    subjectId?: string | null;
    client?: Record<string, unknown>;
    /** The session's `token`; replaces the project key for this call. */
    sessionToken?: string | null;
  }): Promise<VerifyResult> {
    const form = new FormData();
    if (options.subjectId) form.set("subject_id", options.subjectId);
    form.set(
      "meta",
      JSON.stringify({
        frames: options.frames.map((f) => ({ kind: f.kind, ts_ms: f.tsMs })),
        challenge_durations_ms: options.challengeDurationsMs,
        client: options.client ?? {},
      }),
    );
    for (const f of options.frames) form.append("frames", f.jpeg, `${f.kind}.jpg`);
    const { status, body } = await this.request(
      `/v1/sessions/${options.sessionId}/verify`,
      { method: "POST", body: form },
      options.sessionToken,
    );
    if (status !== 200) {
      const detail = (body as { detail?: unknown })?.detail;
      return {
        ok: false,
        mode: "verify",
        reasonCode: reasonCode(body, status),
        scores: toScores(undefined),
        verificationId: null,
        message: typeof detail === "string" ? detail : undefined,
      };
    }
    const j = body as Record<string, unknown>;
    return {
      ok: j.ok as boolean,
      mode: (j.mode as string) ?? "verify",
      reasonCode: j.reason_code as string,
      scores: toScores(j.scores as Record<string, unknown>),
      verificationId: (j.verification_id as number | null) ?? null,
    };
  }

  /**
   * Enrols one photo. With `enrolToken` (from `POST /v1/subjects/tokens` on your backend) the
   * subject, name, replace and ttl were fixed when the token was issued and no API key is needed.
   */
  async enroll(options: {
    photo: Blob;
    externalId?: string;
    name?: string;
    replace?: boolean;
    /** Retention in seconds; undefined uses the policy's `subject_ttl_seconds`, 0 keeps until deleted. */
    ttlSeconds?: number;
    enrolToken?: string | null;
  }): Promise<Subject> {
    const form = new FormData();
    if (options.externalId) form.set("external_id", options.externalId);
    if (!options.enrolToken) {
      form.set("name", options.name ?? "");
      form.set("replace", String(options.replace ?? false));
      if (options.ttlSeconds !== undefined) form.set("ttl_seconds", String(options.ttlSeconds));
    }
    form.set("photo", options.photo, "photo.jpg");
    const { status, body } = await this.request("/v1/subjects", { method: "POST", body: form }, options.enrolToken);
    if (status >= 400) throw new LumifaceError(reasonCode(body, status), body);
    return toSubject(body as Record<string, unknown>);
  }

  /**
   * Issues a single-use enrol token for a device. Backend only: needs the project key. The token
   * binds the identity, not the face, so issue it only for a user you have authenticated yourself;
   * it cannot replace an existing face.
   */
  async createEnrolToken(options: {
    externalId: string;
    name?: string;
    ttlSeconds?: number;
    tokenTtlSeconds?: number;
  }): Promise<{ token: string; externalId: string; expiresAt: string }> {
    const j = await this.json<Record<string, unknown>>(
      "/v1/subjects/tokens",
      this.jsonInit("POST", {
        external_id: options.externalId,
        name: options.name ?? "",
        ttl_seconds: options.ttlSeconds ?? null,
        token_ttl_seconds: options.tokenTtlSeconds ?? null,
      }),
    );
    return { token: j.token as string, externalId: j.external_id as string, expiresAt: j.expires_at as string };
  }

  async listSubjects(): Promise<Subject[]> {
    const rows = await this.json<Record<string, unknown>[]>("/v1/subjects");
    return rows.map(toSubject);
  }

  async getSubject(externalId: string): Promise<Subject> {
    return toSubject(await this.json<Record<string, unknown>>(`/v1/subjects/${encodeURIComponent(externalId)}`));
  }

  async deleteSubject(externalId: string): Promise<void> {
    await this.json(`/v1/subjects/${encodeURIComponent(externalId)}`, { method: "DELETE" });
  }

  async listVerifications(
    filter: { subjectId?: string; purpose?: string; ok?: boolean; limit?: number } = {},
  ): Promise<VerificationRecord[]> {
    const q = new URLSearchParams();
    if (filter.subjectId) q.set("subject_id", filter.subjectId);
    if (filter.purpose) q.set("purpose", filter.purpose);
    if (filter.ok !== undefined) q.set("ok", String(filter.ok));
    q.set("limit", String(filter.limit ?? 100));
    const rows = await this.json<Record<string, unknown>[]>(`/v1/verifications?${q}`);
    return rows.map((j) => ({
      id: j.id as number,
      subjectId: (j.subject_id as string | null) ?? null,
      purpose: (j.purpose as string) ?? "",
      ok: j.ok as boolean,
      reasonCode: j.reason_code as string,
      createdAt: j.created_at as string,
      scores: {
        match: (j.match_score as number | null) ?? null,
        spoof: (j.spoof_score as number | null) ?? null,
        consistency: (j.consistency_score as number | null) ?? null,
      },
    }));
  }

  getPolicy(): Promise<ProjectPolicy> {
    return this.json<ProjectPolicy>("/v1/policy");
  }

  /** Switches the preset and/or merges overrides into the project's policy. */
  updatePolicy(update: { preset?: string; overrides?: Record<string, unknown>; merge?: boolean }): Promise<ProjectPolicy> {
    return this.json<ProjectPolicy>("/v1/policy", this.jsonInit("PUT", { merge: true, ...update }));
  }

  resetPolicy(): Promise<ProjectPolicy> {
    return this.json<ProjectPolicy>("/v1/policy", { method: "DELETE" });
  }

  listPresets(): Promise<PolicyPreset[]> {
    return this.json<PolicyPreset[]>("/v1/policy/presets");
  }
}
