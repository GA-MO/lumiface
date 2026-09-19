import { useMemo, useRef } from "react";
import { LumifaceClient, LumifaceView, type Challenge, type FaceSession, type LivenessState, type VerifyResult, type VerifyStream } from "@lumiface/react";
import type { DemoLine } from "./live-demo";

const PALETTE = ["ff0000", "00ff00", "0000ff", "ff00ff", "ffff00", "00ffff"];

function pick<T>(items: T[], n: number): T[] {
  const copy = [...items];
  const out: T[] = [];
  while (out.length < n && copy.length) out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0]);
  return out;
}

/** Plays the server's part in the browser: the plan (the oval, three colours), then lets the flow end.
 *  It judges nothing, so a replayed video gets through it; the real server reads the walk, the flash
 *  reflection, the passive anti-spoof and the identity from the frames. What it does show is the
 *  protocol: every event the SDK sends, and how many frames went with it. */
class StandInClient extends LumifaceClient {
  onEvent: (line: string) => void = () => {};
  frames = 0;

  constructor() {
    super({ baseUrl: "stand-in" });
  }

  /** What a backend would return from `POST /v1/sessions`; here the browser makes it up. */
  async createSession(): Promise<FaceSession> {
    return { id: Math.random().toString(16).slice(2, 6), token: "", mode: "liveness", purpose: "demo", ttlSeconds: 60, clientConfig: null };
  }

  /** Plays the server's side of the stream: the balanced plan (the oval, then three colours), swallows frames, lets the flow end. */
  override openStream(_session: FaceSession, _clientInfo: Record<string, unknown> = {}, format = "jpeg"): VerifyStream {
    const challenges: Challenge[] = ["face_move"];
    this.onEvent(`recording as ${format}, chunks every 250 ms`);
    const flashColors = pick(PALETTE, 3);
    this.frames = 0;
    const t0 = performance.now();
    const at = () => `${((performance.now() - t0) / 1000).toFixed(1)}s`;
    return {
      plan: Promise.resolve({ challenges, flashColors, flashHoldMs: 450, clientConfig: null, oval: { cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35 } }),
      sendChunk: () => {
        this.frames++;
      },
      event: (name, _ts, index) => {
        this.onEvent(`${at()}  ▶ ${name}${index === undefined ? "" : ` ${index}`}${name === "flash" ? `  #${flashColors[index ?? 0]}` : ""}  · ${this.frames} chunks so far`);
      },
      end: async () => {
        this.onEvent(`${at()}  ▶ end  · ${this.frames} chunks`);
        await new Promise((r) => setTimeout(r, 600));
        return { ok: true, mode: "liveness", reasonCode: "OK", scores: { match: null, spoof: null, consistency: null }, verificationId: this.frames };
      },
      close: () => {},
    };
  }
}

export default function LiveDemoRunner({ landscape, onLine, onClose }: { landscape: boolean; onLine: (line: DemoLine) => void; onClose: () => void }) {
  const client = useMemo(() => new StandInClient(), []);
  const last = useRef<LivenessState | null>(null);
  client.onEvent = (text) => onLine({ kind: "ok", text });

  const onStateChanged = (s: LivenessState) => {
    const prev = last.current;
    last.current = s;
    if (prev?.phase === s.phase) return;
    if (s.phase === "starting") onLine({ kind: "info", text: "Opening the camera, loading BlazeFace (tfjs, WASM)" });
    if (s.phase === "aligning") onLine({ kind: "step", text: "plan  face_move into the oval, then 3 colours · the recording starts here" });
    if (s.phase === "challenge" && prev?.phase === "aligning") onLine({ kind: "step", text: "face_move  walk in until the face fills the oval" });
    if (s.phase === "flash") onLine({ kind: "step", text: "flash  3 colours, 450 ms each, frames keep streaming" });
    if (s.phase === "uploading") onLine({ kind: "step", text: "end  a real server answers from the frames" });
    if (s.phase === "success") {
      onLine({ kind: "info", text: "stand-in: no verdict. The server would now read the walk (growth, fill), the flash reflection, MiniFASNet + CVPR-2024 and the ArcFace match from these frames" });
    }
    if (s.phase === "failed") onLine({ kind: "fail", text: `failed on the device  ${s.result?.reasonCode}` });
  };

  return (
    <LumifaceView
      client={client}
      flow="liveness"
      sessionProvider={() => client.createSession()}
      theme={landscape ? { guideWidthFraction: 0.34, guideCenterY: 0.48 } : {}}
      camera={{ modelUrl: `${import.meta.env.BASE_URL}models/face_detection_short/model.json` }}
      onStateChanged={onStateChanged}
      onResult={() => {}}
      onDone={onClose}
      renderPrompt={(s) => (
        <div className="pointer-events-none flex justify-center px-4 pb-5">
          <span className={`rounded-full px-4 py-2 text-center text-[15px] font-semibold text-white shadow-lg backdrop-blur ${s.state.phase === "failed" ? "bg-red-600/85" : "bg-black/60"}`}>
            {s.state.phase === "success" ? "Flow complete. Nothing was judged: this is a stand-in server." : s.message}
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
