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
  apiKey: string;
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
  };
}

/** Thin client for the Lumiface server. One instance per project API key. */
export class LumifaceClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: LumifaceClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.fetchImpl = options.fetch ?? fetch.bind(globalThis);
  }

  private async request(path: string, init: RequestInit = {}): Promise<{ status: number; body: unknown }> {
    const headers = new Headers(init.headers);
    headers.set("X-API-Key", this.apiKey);
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
    return {
      id: j.session_id as string,
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

  async verify(options: {
    sessionId: string;
    frames: CapturedFrame[];
    challengeDurationsMs: number[];
    subjectId?: string | null;
    client?: Record<string, unknown>;
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
    const { status, body } = await this.request(`/v1/sessions/${options.sessionId}/verify`, {
      method: "POST",
      body: form,
    });
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

  async enroll(options: { externalId: string; photo: Blob; name?: string; replace?: boolean }): Promise<Subject> {
    const form = new FormData();
    form.set("external_id", options.externalId);
    form.set("name", options.name ?? "");
    form.set("replace", String(options.replace ?? false));
    form.set("photo", options.photo, "photo.jpg");
    const j = await this.json<Record<string, unknown>>("/v1/subjects", { method: "POST", body: form });
    return toSubject(j);
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
