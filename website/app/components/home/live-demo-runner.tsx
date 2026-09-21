import { useMemo, useRef } from "react";
import { LumifaceClient, LumifaceView, sessionFromJson, type FaceSession, type LivenessState, type StreamFormat, type VerifyResult, type VerifyStream } from "@lumiface/react";
import { DEMO_URL } from "./demo-config";
import type { DemoLine } from "./live-demo";

const PALETTE = ["ff0000", "00ff00", "0000ff", "ff00ff", "ffff00", "00ffff"];
const STAND_IN = "stand-in";
/** Codes the SDK sets itself; everything else in a result is the server's verdict. */
const DEVICE_CODES = new Set(["FACE_LOST", "TIMEOUT", "CANCELLED", "NETWORK_ERROR", "CAPTURE_ERROR"]);

function pick<T>(items: T[], n: number): T[] {
  const copy = [...items];
  const out: T[] = [];
  while (out.length < n && copy.length) out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0]);
  return out;
}

/** Plays the server's part in the browser when there is no demo backend: the plan (the oval, three colours), then
 *  lets the flow end. It judges nothing, so a replayed video gets through it. */
function standInStream(): VerifyStream {
  let chunks = 0;
  return {
    plan: Promise.resolve({ challenges: ["face_move"], flashColors: pick(PALETTE, 3), flashHoldMs: 450, clientConfig: null, oval: { cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35 } }),
    sendChunk: () => {
      chunks++;
    },
    event: () => {},
    end: async () => {
      await new Promise((r) => setTimeout(r, 600));
      return { ok: true, mode: "liveness", reasonCode: "OK", scores: { match: null, spoof: null, consistency: null }, verificationId: chunks };
    },
    close: () => {},
  };
}

/** The demo's client. With a demo backend (`VITE_LUMIFACE_DEMO_URL`) it is the documented setup: the backend holds
 *  the key and mints the session, the browser streams to the server the backend named, and the backend reads the
 *  verdict afterwards. Without one, or when it does not answer, the stand-in plays the server and judges nothing.
 *  Either way every stream is tapped so the log shows the protocol: each event the SDK sends and how many chunks went with it. */
class DemoClient extends LumifaceClient {
  onEvent: (line: string) => void = () => {};
  standIn = !DEMO_URL;
  private real: LumifaceClient | null = null;

  constructor() {
    super({ baseUrl: "demo" });
  }

  /** What `sessionProvider` returns: the demo backend's session, or a made-up one for the stand-in. */
  async createSession(): Promise<FaceSession> {
    if (DEMO_URL) {
      // The demo machines stop when idle; the first visitor after a pause waits while they start and load the models.
      const waking = setTimeout(() => this.onEvent("backend  waking the demo server (it sleeps when idle, up to a minute)"), 3000);
      try {
        const r = await fetch(`${DEMO_URL}/demo/session`, { method: "POST" });
        clearTimeout(waking);
        if (r.ok) {
          const j = (await r.json()) as { server: string; session: Record<string, unknown> };
          this.real = new LumifaceClient({ baseUrl: j.server });
          this.standIn = false;
          this.onEvent(`backend  POST /demo/session → liveness session, stream to ${new URL(j.server).host}`);
          return sessionFromJson(j.session);
        }
        this.onEvent(r.status === 429 ? "backend  rate limited: the stand-in runs instead, nothing judged" : `backend  answered ${r.status}: the stand-in runs instead, nothing judged`);
      } catch {
        clearTimeout(waking);
        this.onEvent("backend  unreachable: the stand-in runs instead, nothing judged");
      }
    }
    this.standIn = true;
    return { id: Math.random().toString(16).slice(2, 6), token: "", mode: "liveness", purpose: STAND_IN, ttlSeconds: 60, clientConfig: null };
  }

  /** The backend's side of the verdict: read with the key, never taken from the device. */
  async done(sessionId: string): Promise<{ ok: boolean; reason_code: string | null }> {
    const r = await fetch(`${DEMO_URL}/demo/done`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ session_id: sessionId }) });
    if (!r.ok) throw new Error(`${r.status}`);
    return (await r.json()) as { ok: boolean; reason_code: string | null };
  }

  override openStream(session: FaceSession, clientInfo: Record<string, unknown> = {}, format: StreamFormat = "jpeg"): VerifyStream {
    const s = session.purpose === STAND_IN || !this.real ? standInStream() : this.real.openStream(session, clientInfo, format);
    let chunks = 0;
    let colours: string[] = [];
    const t0 = performance.now();
    const at = () => `${((performance.now() - t0) / 1000).toFixed(1)}s`;
    this.onEvent(`recording as ${format}, chunks every 250 ms`);
    // The server holds the plan until its models are loaded, which takes a while right after it wakes.
    const loading = setTimeout(() => this.onEvent("server  loading its models before it sends the plan"), 3000);
    void s.plan.then(
      (p) => {
        clearTimeout(loading);
        colours = p.flashColors;
        this.onEvent(`${at()}  ◀ plan  ${p.challenges.join(", ")} into the oval, then ${p.flashColors.length} colours`);
      },
      () => clearTimeout(loading),
    );
    return {
      plan: s.plan,
      sendChunk: (data, tsMs) => {
        chunks++;
        s.sendChunk(data, tsMs);
      },
      event: (name, tsMs, index) => {
        this.onEvent(`${at()}  ▶ ${name}${index === undefined ? "" : ` ${index}`}${name === "flash" ? `  #${colours[index ?? 0] ?? ""}` : ""}  · ${chunks} chunks so far`);
        s.event(name, tsMs, index);
      },
      end: async () => {
        this.onEvent(`${at()}  ▶ end  · ${chunks} chunks`);
        const r = await s.end();
        if (!this.standIn) this.onEvent(`${at()}  ◀ result  ok=${r.ok} ${r.reasonCode}`);
        return r;
      },
      close: () => s.close(),
    };
  }
}

export default function LiveDemoRunner({ landscape, onLine, onClose }: { landscape: boolean; onLine: (line: DemoLine) => void; onClose: () => void }) {
  const client = useMemo(() => new DemoClient(), []);
  const last = useRef<LivenessState | null>(null);
  client.onEvent = (text) => onLine({ kind: "ok", text });

  const onStateChanged = (s: LivenessState) => {
    const prev = last.current;
    last.current = s;
    if (prev?.phase === s.phase) return;
    if (s.phase === "starting") onLine({ kind: "info", text: `Opening the camera, loading BlazeFace (tfjs, WASM), asking ${DEMO_URL ? "the demo backend" : "the stand-in"} for a session` });
    if (s.phase === "aligning") onLine({ kind: "step", text: "aligning  the recording starts here, clocked by the server" });
    if (s.phase === "challenge" && prev?.phase === "aligning") onLine({ kind: "step", text: "face_move  walk in until the face fills the oval" });
    if (s.phase === "flash") onLine({ kind: "step", text: "flash  the screen colours in turn, frames keep streaming" });
    if (s.phase === "uploading") onLine({ kind: "step", text: client.standIn ? "end  a real server would answer from the frames" : "end  the server judges the walk, the flash and the anti-spoof models" });
    if (s.phase === "success" && client.standIn) {
      onLine({ kind: "info", text: "stand-in: no verdict. A real server would now read the walk (growth, fill), the flash reflection, MiniFASNet + CVPR-2024 and the ArcFace match from these frames" });
    }
    if (s.phase === "failed") {
      const code = s.result?.reasonCode ?? "";
      onLine({ kind: "fail", text: DEVICE_CODES.has(code) || client.standIn ? `failed on the device  ${code}` : `server verdict  ${code}` });
    }
  };

  const onResult = (r: VerifyResult) => {
    if (client.standIn || !r.sessionId || DEVICE_CODES.has(r.reasonCode)) return;
    client
      .done(r.sessionId)
      .then((d) => onLine({ kind: d.ok ? "ok" : "fail", text: `backend  POST /demo/done → ok=${d.ok} ${d.reason_code ?? ""}  · read with the key, this is what a backend acts on` }))
      .catch(() => onLine({ kind: "fail", text: "backend  could not read the verdict" }));
  };

  return (
    <LumifaceView
      client={client}
      flow="liveness"
      sessionProvider={() => client.createSession()}
      theme={landscape ? { guideWidthFraction: 0.34, guideCenterY: 0.48 } : {}}
      camera={{ modelUrl: `${import.meta.env.BASE_URL}models/face_detection_short/model.json` }}
      onStateChanged={onStateChanged}
      onResult={onResult}
      onDone={onClose}
      // The whole viewport, not the demo box: the flash reflection the server reads scales with the lit area. It stays
      // inside the view (no portal): while the stage is full screen, nothing outside the fullscreen element is shown.
      renderFlash={(s) => <div style={{ position: "fixed", inset: 0, zIndex: 9999, background: `#${s.state.flashColor}` }} />}
      renderPrompt={(s) => (
        <div className="pointer-events-none flex justify-center px-4 pb-5">
          <span className={`rounded-full px-4 py-2 text-center text-[15px] font-semibold text-white shadow-lg backdrop-blur ${s.state.phase === "failed" ? "bg-red-600/85" : "bg-black/60"}`}>
            {s.state.phase === "success" ? (client.standIn ? "Flow complete. Nothing was judged: this is a stand-in server." : "A real person: the demo server passed every gate.") : s.message}
          </span>
        </div>
      )}
      renderResult={(s) => (
        <div className="flex justify-center pb-5">
          <button type="button" onClick={onClose} className="rounded-full bg-white px-5 py-2 text-sm font-medium text-[#0d0d18] hover:bg-white/90">
            {s.state.phase === "success" ? s.strings.done : s.strings.retry}
          </button>
        </div>
      )}
      renderError={(e) => <div className="grid h-full place-items-center p-6 text-center text-sm text-white/80">Camera unavailable: {e.message}</div>}
    />
  );
}
