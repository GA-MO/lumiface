import { useMemo, useRef } from "react";
import { FacegateClient, FacegateView, type CapturedFrame, type Challenge, type FaceSession, type LivenessState, type VerifyResult } from "@facegate/react";
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
class StandInClient extends FacegateClient {
  constructor() {
    super({ baseUrl: "stand-in", apiKey: "none" });
  }

  override async createSession(): Promise<FaceSession> {
    const challenges = ["smile" as Challenge, ...pick(POOL.filter((c) => c !== "smile"), 1)].sort(() => Math.random() - 0.5);
    const flashColors = pick(PALETTE, 3);
    return {
      id: Math.random().toString(16).slice(2, 6),
      mode: "liveness",
      purpose: "demo",
      challenges,
      frameKinds: ["neutral_start", ...challenges.map((_, i) => `challenge_${i}`), ...flashColors.map((_, i) => `flash_${i}`), "neutral_end"],
      ttlSeconds: 60,
      flashColors,
      flashHoldMs: 450,
      clientConfig: null,
    };
  }

  override async verify(options: { frames: CapturedFrame[] }): Promise<VerifyResult> {
    await new Promise((r) => setTimeout(r, 600));
    return { ok: true, mode: "liveness", reasonCode: "OK", scores: { match: null, spoof: null, consistency: null }, verificationId: options.frames.length };
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
    <FacegateView
      client={client}
      purpose="demo"
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
          <button type="button" onClick={onClose} className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black shadow-sm hover:bg-white/90">
            {s.state.phase === "success" ? s.strings.done : s.strings.retry}
          </button>
        </div>
      )}
      renderError={(e) => <div className="grid h-full place-items-center p-6 text-center text-sm text-white/80">Camera unavailable: {e.message}</div>}
    />
  );
}
