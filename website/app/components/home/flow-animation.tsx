import { Check, KeyRound, ScanFace, Server, Smartphone } from "lucide-react";

const T = "12s";

// Percent of the loop. 0-6: backend mints the session. 6-72: the device streams. 72-97: the server finishes. 97: verdict.
const PROMPTS = [
  { text: "Move back a little", from: 6, to: 10, color: "#fff" },
  { text: "Hold still", from: 10, to: 14, color: "#fff" },
  { text: "Move closer until your face fills the oval", from: 14, to: 40, color: "#ffc107" },
  { text: "Hold still", from: 40, to: 72, color: "#fff" },
  { text: "Checking", from: 72, to: 97, color: "#fff" },
  { text: "Verified", from: 97, to: 100, color: "#4caf50" },
];

const FLASHES = [
  { color: "#ff0000", from: 54, to: 60 },
  { color: "#00ff00", from: 60, to: 66 },
  { color: "#0000ff", from: 66, to: 72 },
];

/** Events the device sends over the stream, at the boundary each one marks. */
const EVENTS = [
  { text: "aligned", at: 14 },
  { text: "challenge_done 0", at: 40 },
  { text: "flash 0 · 1 · 2", at: 60 },
  { text: "flash_end", at: 72 },
  { text: "end", at: 74 },
];

/** What the server reads from its own frames, as it happens, then the gates it runs at the end. */
const GATES = [
  { name: "Move seen", detail: "face box grew 0.42 → 0.58 of the frame, into the oval", at: 38 },
  { name: "Flash reflection", detail: "cheeks follow the 3 colours, wall does not", at: 76 },
  { name: "Server clock", detail: "2.6 s into the oval, no repeated frames", at: 80 },
  { name: "MiniFASNet + CVPR-2024", detail: "print, screen and bezel-free replay", at: 86 },
  { name: "ArcFace match", detail: "key frames vs the enrolled face", at: 92 },
];

const BACKEND = [
  { text: "POST /v1/sessions  →  session_token", from: 0, to: 6 },
  { text: "GET /v1/sessions/{id}  →  ok", from: 97, to: 100 },
];

function windowKeyframes(name: string, from: number, to: number, on: string, off: string) {
  const pre = from > 0 ? `0%,${from - 0.01}%{${off}}` : "";
  const post = to < 100 ? `${to + 0.01}%,100%{${off}}` : "";
  return `@keyframes ${name}{${pre}${from}%,${to}%{${on}}${post}}`;
}

const css = [
  `.fa *{animation-duration:${T};animation-iteration-count:infinite;animation-timing-function:linear}`,
  ...PROMPTS.map((p, i) => windowKeyframes(`fa-prompt-${i}`, p.from, p.to, "opacity:1", "opacity:0")),
  ...FLASHES.map((f, i) => windowKeyframes(`fa-flash-${i}`, f.from, f.to, "opacity:1", "opacity:0")),
  ...GATES.map((g, i) => windowKeyframes(`fa-gate-${i}`, g.at, 100, "opacity:1;transform:scale(1)", "opacity:0;transform:scale(0.4)")),
  ...GATES.map((g, i) => windowKeyframes(`fa-gate-row-${i}`, g.at, 100, "border-color:color-mix(in oklab,#10b981 45%,transparent);background:color-mix(in oklab,#10b981 8%,transparent)", "border-color:var(--color-fd-border);background:transparent")),
  ...EVENTS.map((e, i) => windowKeyframes(`fa-event-${i}`, e.at, Math.min(e.at + 5, 100), "opacity:1;transform:translateY(0)", "opacity:0;transform:translateY(4px)")),
  ...BACKEND.map((b, i) => windowKeyframes(`fa-backend-${i}`, b.from, b.to, "opacity:1", "opacity:0.35")),
  `@keyframes fa-guide{0%,13.99%{stroke:#fff}14%,53.99%{stroke:#ffc107}54%,96.99%{stroke:#fff}97%,100%{stroke:#4caf50}}`,
  windowKeyframes("fa-result", 97, 100, "opacity:1;transform:translateY(0)", "opacity:0;transform:translateY(6px)"),
  windowKeyframes("fa-wire-on", 6, 74, "opacity:1", "opacity:0.25"),
  `@keyframes fa-dash{to{stroke-dashoffset:-48}}`,
  // Frames flow the whole time the device streams (6-74%), a packet every ~1.4% of the loop.
  ...Array.from({ length: 12 }, (_, i) => `@keyframes fa-packet-${i}{0%,${6 + i * 1.4}%{offset-distance:0%;opacity:0}${6.5 + i * 1.4}%{opacity:1}${9 + i * 1.4}%{offset-distance:100%;opacity:1}${9.5 + i * 1.4}%,${9.5 + i * 1.4 + 0.01}%{offset-distance:0%;opacity:0}${9.5 + i * 1.4 + 0.02}%,100%{offset-distance:0%;opacity:0}}`),
  windowKeyframes("fa-progress-1", 40, 100, "background:#fff", "background:rgba(255,255,255,0.25)"),
  windowKeyframes("fa-progress-2", 72, 100, "background:#fff", "background:rgba(255,255,255,0.25)"),
  // The face: a normal selfie distance, "move back" to the start, hold, then the walk that fills the oval.
  `@keyframes fa-head{0%,6%{transform:scale(0.95)}10%,14%{transform:scale(0.72)}40%,100%{transform:scale(1.32)}}`,
  `@media (prefers-reduced-motion: reduce){.fa *{animation-play-state:paused}}`,
].join("\n");

function Wire({ vertical }: { vertical: boolean }) {
  const d = vertical ? "M30 4 L30 116" : "M4 30 L236 30";
  return (
    <svg viewBox={vertical ? "0 0 60 120" : "0 0 240 60"} className={vertical ? "mx-auto h-28 w-16" : "h-16 w-full"} aria-hidden>
      <path d={d} fill="none" stroke="var(--color-fd-border)" strokeWidth="2" />
      <path d={d} fill="none" stroke="var(--color-brand)" strokeWidth="2" strokeDasharray="8 8" style={{ animationName: "fa-dash, fa-wire-on", animationDuration: "1s, " + T }} />
      {Array.from({ length: 12 }, (_, i) => (
        <circle key={i} r="3" fill="var(--color-brand)" style={{ offsetPath: `path('${d}')`, animationName: `fa-packet-${i}`, animationDuration: T, animationIterationCount: "infinite" }} />
      ))}
    </svg>
  );
}

/** The whole flow on a loop: the backend mints a session, the device streams the walk into the oval and the flash, the server reads both from its own frames, the backend fetches the verdict. */
export function FlowAnimation() {
  return (
    <div className="fa mt-12 rounded-3xl border border-fd-border bg-fd-card p-6 sm:p-8">
      <style>{css}</style>

      <div className="mb-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs">
        <span className="flex items-center gap-2 font-medium">
          <KeyRound className="h-4 w-4 text-brand" />
          Your backend, with the project key
        </span>
        {BACKEND.map((b, i) => (
          <span key={b.text} className="rounded-full border border-fd-border px-3 py-1 font-mono text-[11px] text-fd-muted-foreground" style={{ animationName: `fa-backend-${i}` }}>
            {b.text}
          </span>
        ))}
      </div>

      <div className="grid items-center gap-4 sm:grid-cols-[auto_1fr_auto] sm:gap-6">

      <div className="flex flex-col items-center gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Smartphone className="h-4 w-4 text-brand" />
          On the device
        </div>
        <div className="relative aspect-[9/17] w-[150px] overflow-hidden rounded-[1.4rem] border-[5px] border-[#1d1f2c] bg-[#232c38]">
          <svg viewBox="0 0 90 170" className="absolute inset-0 h-full w-full" aria-hidden>
            <rect width="90" height="170" fill="#2b3542" />
            <path d="M-10 170 V138 C10 118 30 112 45 112 C60 112 80 118 100 138 V170 Z" fill="#3a4554" />
            <g style={{ animationName: "fa-head", transformOrigin: "45px 72px" }}>
              <rect x="39" y="90" width="12" height="20" rx="5" fill="#6b7a8c" />
              <ellipse cx="45" cy="70" rx="22" ry="27" fill="#7d8ca0" />
              <ellipse cx="37" cy="62" rx="3" ry="2" fill="#1f2730" />
              <ellipse cx="53" cy="62" rx="3" ry="2" fill="#1f2730" />
              <path d="M38 78 Q45 80 52 78" fill="none" stroke="#1f2730" strokeWidth="1.5" strokeLinecap="round" />
            </g>
            <rect x="0" y="0" width="90" height="170" fill="rgba(0,0,0,0.5)" mask="url(#fa-cut)" />
            <defs>
              <mask id="fa-cut">
                <rect width="90" height="170" fill="#fff" />
                <ellipse cx="45" cy="72" rx="32" ry="43" fill="#000" />
              </mask>
            </defs>
            <ellipse cx="45" cy="72" rx="32" ry="43" fill="none" strokeWidth="2.5" style={{ animationName: "fa-guide" }} />
          </svg>
          {FLASHES.map((f, i) => (
            <div key={f.color} className="absolute inset-0" style={{ background: f.color, animationName: `fa-flash-${i}` }} />
          ))}
          <div className="absolute inset-x-0 top-3 flex justify-center gap-1">
            {[1, 2].map((n) => (
              <span key={n} className="h-1 w-5 rounded-full" style={{ animationName: `fa-progress-${n}` }} />
            ))}
          </div>
          {PROMPTS.map((p, i) => (
            <div key={p.text} className="absolute inset-x-0 bottom-4 text-center text-[11px] font-semibold" style={{ color: p.color, animationName: `fa-prompt-${i}` }}>
              {p.text}
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-fd-muted-foreground">Guides the person; decides nothing</p>
      </div>

      <div className="min-w-0">
        <div className="hidden sm:block">
          <Wire vertical={false} />
        </div>
        <div className="sm:hidden">
          <Wire vertical />
        </div>
        <div className="relative h-6 text-center font-mono text-[10px] text-fd-muted-foreground">
          {EVENTS.map((e, i) => (
            <span key={e.text} className="absolute inset-x-0 rounded border border-fd-border px-1 py-px" style={{ animationName: `fa-event-${i}`, width: "fit-content", margin: "0 auto" }}>
              {e.text}
            </span>
          ))}
        </div>
        <p className="mt-2 text-center font-mono text-[10px] text-fd-muted-foreground">WS /v1/sessions/…/stream · video chunks (VP8 / H.264) + events · session token</p>
        <p className="mt-1 text-center text-[11px] text-fd-muted-foreground">Decoded into frames, stamped with the server's clock on arrival</p>
      </div>

      <div className="w-full sm:w-[280px]">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Server className="h-4 w-4 text-brand" />
          Lumiface server, from its own frames
        </div>
        <ul className="mt-3 space-y-2">
          {GATES.map((g, i) => (
            <li key={g.name} className="flex items-center gap-3 rounded-xl border px-3 py-2" style={{ animationName: `fa-gate-row-${i}` }}>
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-500 text-white" style={{ animationName: `fa-gate-${i}` }}>
                <Check className="h-3 w-3" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium leading-tight">{g.name}</span>
                <span className="block truncate text-[11px] text-fd-muted-foreground">{g.detail}</span>
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400" style={{ animationName: "fa-result" }}>
          <ScanFace className="h-4 w-4" />
          OK · verified E001 · match 0.82
        </div>
      </div>
      </div>
    </div>
  );
}
