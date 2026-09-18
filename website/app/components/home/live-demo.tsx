import { lazy, Suspense, useEffect, useState } from "react";

const Runner = lazy(() => import("./live-demo-runner"));

function Placeholder({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="max-w-xs text-sm text-fd-muted-foreground">
        Runs the real React SDK in this tab: MediaPipe on your camera, the real challenge state machine, a stand-in for the
        server. Nothing is uploaded.
      </p>
      <button
        type="button"
        onClick={onStart}
        className="rounded-lg bg-fd-primary px-5 py-2.5 font-medium text-fd-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary"
      >
        Try it with your camera
      </button>
    </div>
  );
}

export function LiveDemo() {
  const [mounted, setMounted] = useState(false);
  const [running, setRunning] = useState(false);
  useEffect(() => setMounted(true), []);
  return (
    <div className="grid gap-6 sm:grid-cols-[minmax(200px,260px)_1fr]">
      <div className="relative mx-auto aspect-[9/17] w-full max-w-[260px] overflow-hidden rounded-[2rem] border-[6px] border-[#141a24] bg-[#141a24] shadow-2xl">
        <div className="h-full w-full overflow-hidden rounded-[1.6rem] bg-[#0f141c]">
          {mounted && running ? (
            <Suspense fallback={<div className="grid h-full place-items-center text-sm text-white/70">Loading the SDK</div>}>
              <Runner onClose={() => setRunning(false)} />
            </Suspense>
          ) : (
            <Placeholder onStart={() => setRunning(true)} />
          )}
        </div>
      </div>
      <div id="live-demo-log" className="rounded-xl border border-fd-border bg-fd-card p-4">
        <p className="mb-2 text-xs text-fd-muted-foreground">What the state machine reports</p>
        <ul id="live-demo-lines" className="min-h-[14.5rem] space-y-0.5 font-mono text-[12.5px] leading-6 text-fd-muted-foreground">
          <li>Waiting for the camera.</li>
        </ul>
      </div>
    </div>
  );
}
