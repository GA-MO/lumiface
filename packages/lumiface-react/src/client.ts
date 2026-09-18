import { Http, planFromJson, reasonCode, toSubject, toVerifyResult } from "./http.ts";
import {
  LumifaceError,
  clientError,
  type FaceSession,
  type StreamEventName,
  type StreamPlan,
  type Subject,
  type VerifyResult,
  type VerifyStream,
} from "./types.ts";

export { planFromJson, sessionFromJson } from "./http.ts";

export interface LumifaceClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
  /** WebSocket constructor; defaults to the browser's. */
  WebSocket?: typeof WebSocket;
}

const MAX_QUEUED_BYTES = 512 * 1024; // beyond this, drop frames instead of adding latency

/**
 * The client a browser ships with. It holds no secret: every call carries a short-lived token
 * that your backend obtained with the project key (`POST /v1/sessions` → `session_token`,
 * `POST /v1/subjects/tokens` → enrol token). Everything the key can do — sessions, subjects,
 * the audit log, the policy — is plain REST for your backend; see `examples/backend`.
 */
export class LumifaceClient {
  private readonly http: Http;
  private readonly baseUrl: string;
  private readonly WebSocketImpl: typeof WebSocket | undefined;

  constructor(options: LumifaceClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.http = new Http(options.baseUrl, options.fetch);
    this.WebSocketImpl = options.WebSocket ?? (typeof WebSocket !== "undefined" ? WebSocket : undefined);
  }

  /**
   * Opens the session's stream. The server answers with the plan; the controller then sends frames
   * and events and finally `end()`s for the verdict.
   */
  openStream(session: FaceSession, clientInfo: Record<string, unknown> = {}): VerifyStream {
    if (!this.WebSocketImpl) throw new Error("no WebSocket implementation available");
    const url = `${this.baseUrl.replace(/^http/, "ws")}/v1/sessions/${session.id}/stream`;
    const ws = new this.WebSocketImpl(url);
    ws.binaryType = "arraybuffer";
    let resolvePlan!: (p: StreamPlan) => void;
    let rejectPlan!: (e: unknown) => void;
    const plan = new Promise<StreamPlan>((res, rej) => {
      resolvePlan = res;
      rejectPlan = rej;
    });
    plan.catch(() => {}); // the controller reads the rejection through end()/plan; keep Node quiet
    let resolveEnd: ((r: VerifyResult) => void) | null = null;
    let outcome: VerifyResult | null = null;
    let settled = false;

    const settle = (r: VerifyResult) => {
      if (settled) return;
      settled = true;
      outcome = r;
      rejectPlan(new LumifaceError(r.reasonCode, r));
      resolveEnd?.(r);
    };
    ws.onopen = () => ws.send(JSON.stringify({ type: "hello", token: session.token, client: clientInfo }));
    ws.onmessage = (m) => {
      if (typeof m.data !== "string") return;
      const j = JSON.parse(m.data) as Record<string, unknown>;
      if (j.type === "plan") resolvePlan(planFromJson(j));
      else if (j.type === "result") settle(toVerifyResult(j));
      else if (j.type === "error") settle({ ...clientError(String(j.reason_code ?? "STREAM_ERROR")), mode: session.mode });
    };
    ws.onerror = () => settle({ ...clientError("NETWORK_ERROR", "stream error"), mode: session.mode });
    ws.onclose = (e) => {
      if (!settled) settle({ ...clientError("NETWORK_ERROR", `stream closed (${e.code})`), mode: session.mode });
    };
    const open = () => ws.readyState === ws.OPEN;
    return {
      plan,
      sendFrame: (jpeg, tsMs) => {
        if (!open() || ws.bufferedAmount > MAX_QUEUED_BYTES) return;
        void jpeg.arrayBuffer().then((buf) => {
          if (!open()) return;
          const out = new Uint8Array(8 + buf.byteLength);
          new DataView(out.buffer).setBigUint64(0, BigInt(Math.max(0, Math.round(tsMs))));
          out.set(new Uint8Array(buf), 8);
          ws.send(out);
        });
      },
      event: (name, tsMs, index) => {
        if (open()) ws.send(JSON.stringify({ type: "event", name, ts: Math.round(tsMs), ...(index === undefined ? {} : { index }) }));
      },
      end: () =>
        new Promise<VerifyResult>((res) => {
          if (outcome) return res(outcome);
          resolveEnd = res;
          if (open()) ws.send(JSON.stringify({ type: "end" }));
        }),
      close: () => {
        if (!settled) settle({ ...clientError("CANCELLED"), mode: session.mode });
        if (ws.readyState === ws.OPEN || ws.readyState === ws.CONNECTING) ws.close();
      },
    };
  }

  /** Enrols one photo as the subject named in `enrolToken`. */
  async enroll(options: { photo: Blob; enrolToken: string }): Promise<Subject> {
    const form = new FormData();
    form.set("photo", options.photo, "photo.jpg");
    const { status, body } = await this.http.request("/v1/subjects", { method: "POST", body: form }, options.enrolToken);
    if (status >= 400) throw new LumifaceError(reasonCode(body, status), body);
    return toSubject(body as Record<string, unknown>);
  }
}
