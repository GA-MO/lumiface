import { Camera, Check, ChevronRight, CircleAlert, Loader2 } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";

const Runner = lazy(() => import("./live-demo-runner"));

export type DemoLine = { kind: "info" | "step" | "ok" | "fail"; text: string };

function Placeholder({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-white/10 text-white">
        <Camera className="h-6 w-6" />
      </span>
      <div>
        <p className="font-display text-lg font-semibold text-white">Try the real SDK</p>
        <p className="mx-auto mt-1 max-w-xs text-sm text-white/60">
          MediaPipe on your camera, the real challenge state machine, a stand-in for the server. Nothing leaves this tab.
        </p>
      </div>
      <button
        type="button"
        onClick={onStart}
        className="rounded-full bg-white px-5 py-2.5 font-medium text-[#0d0d18] hover:bg-white/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-ring"
      >
        Start with my camera
      </button>
    </div>
  );
}

function LineIcon({ kind }: { kind: DemoLine["kind"] }) {
  if (kind === "ok") return <Check className="h-3.5 w-3.5 text-emerald-500" />;
  if (kind === "fail") return <CircleAlert className="h-3.5 w-3.5 text-red-500" />;
  if (kind === "step") return <ChevronRight className="h-3.5 w-3.5 text-brand" />;
  return <Loader2 className="h-3.5 w-3.5 animate-spin text-fd-muted-foreground" />;
}

export function LiveDemo() {
  const [mounted, setMounted] = useState(false);
  const [running, setRunning] = useState(false);
  const [landscape, setLandscape] = useState(true);
  const [lines, setLines] = useState<DemoLine[]>([{ kind: "info", text: "Waiting for the camera" }]);
  useEffect(() => {
    setMounted(true);
    const mq = window.matchMedia("(min-width: 640px)");
    const update = () => setLandscape(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  const push = (line: DemoLine) => setLines((ls) => [...ls.filter((l) => l.kind !== "info"), line].slice(-6));
  return (
    <div className="flex flex-col gap-4">
      <div className="relative mx-auto w-full max-w-[300px] overflow-hidden rounded-[2.2rem] border-[6px] border-[#1d1f2c] bg-[#1d1f2c] shadow-[0_40px_70px_-30px_rgba(0,0,0,0.7)] ring-1 ring-white/10 sm:max-w-none sm:rounded-3xl sm:border-0">
        <div className="hidden items-center gap-1.5 border-b border-white/10 px-4 py-2.5 sm:flex">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-3 font-mono text-[11px] text-white/50">lumiface · live demo · stand-in server</span>
        </div>
        <div className="aspect-[9/16] w-full overflow-hidden rounded-[1.8rem] bg-[#0d0d18] sm:aspect-[4/3] sm:rounded-none">
          {mounted && running ? (
            <Suspense fallback={<div className="grid h-full place-items-center text-sm text-white/70">Loading the SDK</div>}>
              <Runner landscape={landscape} onLine={push} onClose={() => setRunning(false)} />
            </Suspense>
          ) : (
            <Placeholder onStart={() => setRunning(true)} />
          )}
        </div>
      </div>
      <div className="rounded-3xl border border-fd-border bg-fd-card p-4">
        <p className="mb-2 flex items-center justify-between text-xs text-fd-muted-foreground">
          <span>State machine</span>
          <span className="font-mono">onStateChanged</span>
        </p>
        <ul className="h-[9.75rem] space-y-1.5 overflow-hidden text-[13px]">
          {lines.map((l, i) => (
            <li key={i} className={`flex items-start gap-2 ${l.kind === "ok" ? "text-emerald-600 dark:text-emerald-400" : l.kind === "fail" ? "text-red-600 dark:text-red-400" : "text-fd-muted-foreground"}`}>
              <span className="mt-0.5 shrink-0">
                <LineIcon kind={l.kind} />
              </span>
              <span className="font-mono">{l.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
