import { useEffect, useMemo, useRef, useState } from "react";
import { FacegateClient, FacegateView, type CapturedFrame, type Challenge, type FaceSession, type LivenessState, type VerifyResult } from "@facegate/react";

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

function setLines(lines: string[]) {
  const ul = document.getElementById("live-demo-lines");
  if (!ul) return;
  ul.replaceChildren(
    ...lines.map((l) => {
      const li = document.createElement("li");
      li.textContent = l;
      if (l.startsWith("OK")) li.className = "text-emerald-600 dark:text-emerald-400";
      return li;
    }),
  );
}

export default function LiveDemoRunner({ onClose }: { onClose: () => void }) {
  const client = useMemo(() => new StandInClient(), []);
  const [lines, setLinesState] = useState<string[]>(["Opening the camera and loading MediaPipe (first time takes a few seconds)."]);
  const startedAt = useRef<Record<number, number>>({});
  const last = useRef<LivenessState | null>(null);

  useEffect(() => setLines(lines), [lines]);

  const add = (line: string) => setLinesState((ls) => [...ls, line].slice(-9));

  const onStateChanged = (s: LivenessState) => {
    const prev = last.current;
    last.current = s;
    if (prev?.phase !== s.phase) {
      if (s.phase === "aligning") add(`session  ${s.challengeCount} challenges incl. a client-only turn`);
      if (s.phase === "flash") add("flash  filling the screen with 3 server colours");
      if (s.phase === "uploading") add("uploading  neutral_start, challenge frames, flash frames, neutral_end");
      if (s.phase === "success") add(`OK  ${s.result?.verificationId} frames would go to the server`);
      if (s.phase === "failed") add(`failed  ${s.result?.reasonCode}`);
    }
    if (s.phase === "challenge" && s.challenge && prev?.challengeIndex !== s.challengeIndex) {
      startedAt.current[s.challengeIndex] = performance.now();
      if (prev && prev.phase === "challenge" && prev.challenge) {
        add(`challenge_${prev.challengeIndex} ${prev.challenge}  ${Math.round(performance.now() - startedAt.current[prev.challengeIndex])} ms`);
      }
      add(`prompt  ${s.challenge}`);
    }
  };

  return (
    <FacegateView
      client={client}
      purpose="demo"
      showDebug
      onStateChanged={onStateChanged}
      onResult={() => {}}
      onDone={onClose}
      renderError={(e) => <div className="grid h-full place-items-center p-6 text-center text-sm text-white/80">Camera unavailable: {e.message}</div>}
    />
  );
}
