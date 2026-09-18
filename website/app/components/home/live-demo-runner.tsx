import { useMemo, useRef } from "react";
import { LumifaceClient, LumifaceView, type Challenge, type FaceSession, type LivenessState, type VerifyResult, type VerifyStream } from "@lumiface/react";
import type { DemoLine } from "./live-demo";

const POOL: Challenge[] = ["blink", "smile", "turn_left", "turn_right", "nod"];
const PALETTE = ["ff0000", "00ff00", "0000ff", "ff00ff", "ffff00", "00ffff"];

function pick<T>(items: T[], n: number): T[] {
  const copy = [...items];
  const out: T[] = [];
  while (out.length < n && copy.length) out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0]);
  return out;
}

/** Plays the server's part in the browser: random challenges and colours, then an OK. */
class StandInClient extends LumifaceClient {
  constructor() {
    super({ baseUrl: "stand-in" });
  }

  /** What a backend would return from `POST /v1/sessions`; here the browser makes it up. */
  async createSession(): Promise<FaceSession> {
    return { id: Math.random().toString(16).slice(2, 6), token: "", mode: "liveness", purpose: "demo", ttlSeconds: 60, clientConfig: null };
  }

  /** Plays the server's side of the stream: hands out a plan, swallows frames, answers OK at the end. */
  override openStream(): VerifyStream {
    const challenges = ["smile" as Challenge, ...pick(POOL.filter((c) => c !== "smile"), 1)].sort(() => Math.random() - 0.5);
    const flashColors = pick(PALETTE, 3);
    let frames = 0;
    return {
      plan: Promise.resolve({ challenges, flashColors, flashHoldMs: 450, clientConfig: null }),
      sendFrame: () => {
        frames++;
      },
      event: () => {},
      end: async () => {
        await new Promise((r) => setTimeout(r, 600));
        return { ok: true, mode: "liveness", reasonCode: "OK", scores: { match: null, spoof: null, consistency: null }, verificationId: frames };
      },
      close: () => {},
    };
  }
}

export default function LiveDemoRunner({ landscape, onLine, onClose }: { landscape: boolean; onLine: (line: DemoLine) => void; onClose: () => void }) {
  const client = useMemo(() => new StandInClient(), []);
  const startedAt = useRef<Record<number, number>>({});
  const last = useRef<LivenessState | null>(null);

  const onStateChanged = (s: LivenessState) => {
    const prev = last.current;
    last.current = s;
    if (prev?.phase !== s.phase) {
      if (s.phase === "starting") onLine({ kind: "info", text: "Opening the camera, loading MediaPipe" });
      if (s.phase === "aligning") onLine({ kind: "step", text: `session  ${s.challengeCount} challenges, 3 flash colours` });
      if (s.phase === "flash") onLine({ kind: "step", text: "flash  3 server colours, one frame each" });
      if (s.phase === "uploading") onLine({ kind: "step", text: "upload  neutral, challenge and flash frames" });
      if (s.phase === "success") onLine({ kind: "ok", text: `OK  ${s.result?.verificationId} frames verified by the stand-in` });
      if (s.phase === "failed") onLine({ kind: "fail", text: `failed  ${s.result?.reasonCode}` });
    }
    if (s.phase === "challenge" && s.challenge && (prev?.phase !== "challenge" || prev.challengeIndex !== s.challengeIndex)) {
      startedAt.current[s.challengeIndex] = performance.now();
      if (prev && prev.phase === "challenge" && prev.challenge) {
        onLine({ kind: "ok", text: `${prev.challenge}  ${Math.round(performance.now() - startedAt.current[prev.challengeIndex])} ms` });
      }
      onLine({ kind: "step", text: `challenge_${s.challengeIndex}  ${s.challenge}` });
    }
  };

  return (
    <LumifaceView
      client={client}
      flow="liveness"
      sessionProvider={() => client.createSession()}
      theme={landscape ? { guideWidthFraction: 0.34, guideCenterY: 0.48 } : {}}
      onStateChanged={onStateChanged}
      onResult={() => {}}
      onDone={onClose}
      renderPrompt={(s) => (
        <div className="pointer-events-none flex justify-center px-4 pb-5">
          <span className={`rounded-full px-4 py-2 text-[15px] font-semibold text-white shadow-lg backdrop-blur ${s.state.phase === "failed" ? "bg-red-600/85" : s.state.phase === "success" ? "bg-emerald-600/85" : "bg-black/60"}`}>
            {s.message}
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
