import { HomeLayout } from "fumadocs-ui/layouts/home";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Code2,
  Eye,
  Github,
  Globe,
  KeyRound,
  Layers,
  Paintbrush,
  ScanFace,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Sparkles,
  Timer,
  TriangleAlert,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";
import { Code } from "@/components/code";
import { Logo } from "@/components/logo";
import { FlowAnimation } from "@/components/home/flow-animation";
import { PresetSwitch, PRESETS, presetBody } from "@/components/home/preset-switch";
import { LiveDemo } from "@/components/home/live-demo";
import { OverlayVariants, OVERLAY_SNIPPETS } from "@/components/home/overlay-variants";
import { highlightCode, highlightDark } from "@/lib/code.server";
import { baseOptions } from "@/lib/layout.shared";
import { GITHUB_URL } from "@/lib/site";
import type { Route } from "./+types/home";

const TERMINAL = `cd server && uv sync
uv run python weights/download.py && cp .env.example .env
uv run uvicorn app.main:app --port 8000

curl -X POST localhost:8000/v1/sessions -H "X-API-Key: lf_sk_change-me" \\
  -H "Content-Type: application/json" -d "{\\"reference_photo\\": \\"$(base64 -i me.jpg)\\"}"

bun run dev:backend        # examples/backend holds the key
flutter run --release      # examples/flutter, on a phone
bun run dev:react          # examples/react`;

export async function loader() {
  const [terminal, snippets, presetEntries] = await Promise.all([
    highlightDark(TERMINAL, "bash"),
    Promise.all(OVERLAY_SNIPPETS.map((code) => highlightCode(code, "tsx"))),
    Promise.all(Object.keys(PRESETS).map(async (name) => [name, await highlightCode(presetBody(name), "json")] as const)),
  ]);
  return { terminal, snippets, presets: Object.fromEntries(presetEntries) };
}

export function meta() {
  return [
    { title: "Lumiface" },
    { name: "description", content: "Self-hosted face verification with active liveness for Flutter, React and any HTTP client." },
  ];
}

const STATS = [
  ["2", "anti-spoof models", "MiniFASNet + CVPR-2024"],
  ["3", "device detectors", "BlazeFace on web and Android, Apple Vision on iOS"],
  ["42", "policy fields", "tuned per project, no redeploy"],
  ["1", "stream per session", "frames + events over WebSocket, server clock"],
] as const;

const STEPS = [
  { icon: KeyRound, title: "Send the photo you have", body: "Your backend creates the session with the person's photo from its own records. The key never reaches a device; the server keeps no face — the photo lives for that one session." },
  { icon: ScanFace, title: "Stream from the device", body: "The SDK opens the session's stream, gets the plan and sends frames the whole time while it guides the person into the oval and through the flash." },
  { icon: ShieldCheck, title: "Judge on the server", body: "The server clocks the stream itself, reads the move into the oval and the flash from its own detector, runs anti-spoof and identity, and your backend reads the verdict." },
] as const;

const DEVICE_CHECKS: readonly [LucideIcon, string, string][] = [
  [Sparkles, "Guides into the oval", "Move closer until the face fills the oval the server drew; the device tells the person to move back, come closer, hold still. The server re-reads the move itself."],
  [Eye, "A face box is all it needs", "TensorFlow.js BlazeFace in the browser, TensorFlow Lite BlazeFace on Android, Apple Vision on iOS. A face box, nothing more, is all the device needs."],
  [Zap, "Shows the flash", "Three colours from the plan fill the screen in turn while the frames keep flowing; the server reads the reflection."],
  [Timer, "Streams and marks", "About eight frames a second plus a marker at each boundary. The markers say where to look; the device's timestamps only place frames into windows, the server keeps the time."],
];

const SERVER_CHECKS: readonly [LucideIcon, string, string][] = [
  [ScanFace, "Reads the oval itself", "Its own face boxes on the streamed frames: the oval is a face that grew from far into it, centred, inside the window. A patched client cannot skip it."],
  [Timer, "Its own clock", "Every frame and event is stamped on arrival; durations, order and a repeated feed are judged server-side."],
  [Zap, "Flash reflection", "The cheeks must follow the colour sequence in each colour's window and reflect more than the wall behind."],
  [ShieldCheck, "Anti-spoof and identity", "MiniFASNet and the CVPR-2024 ResNet50 on the key frames, then ArcFace against the reference photo and across frames."],
];

const POLICY_POINTS: readonly [LucideIcon, string][] = [
  [SlidersHorizontal, "A project is an API key: one for the attendance app, one for the door, one for a laptop that runs relaxed."],
  [Layers, "Presets for balanced, strict, relaxed and emulator; overrides win field by field."],
  [Zap, "The session carries the client tunables, so the SDK follows the policy without a rebuild."],
];

const PLATFORMS: readonly [LucideIcon, string, string, string][] = [
  [Smartphone, "Flutter", "iOS with Apple Vision, Android with TFLite BlazeFace, the web with TensorFlow.js, from one package.", "/docs/flutter"],
  [Code2, "React", "LumifaceView and useLumiface on React 18 and 19, TensorFlow.js BlazeFace in the browser.", "/docs/react"],
  [Globe, "HTTP", "Any client that can open a camera talks to the same five endpoints.", "/docs/api"],
];

const FOOTER_LINKS: readonly [string, string][] = [
  ["Get started", "/docs/get-started"],
  ["Concepts", "/docs/concepts"],
  ["Flutter", "/docs/flutter"],
  ["React", "/docs/react"],
  ["API", "/docs/api"],
  ["Policy reference", "/docs/policy-reference"],
  ["Security", "/docs/security"],
];

const container = "mx-auto w-full max-w-7xl px-5 sm:px-8";
const pill = "inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-[15px] font-medium no-underline transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-ring";
const primaryButton = `${pill} bg-fd-primary text-fd-primary-foreground hover:opacity-90`;
const secondaryButton = `${pill} border border-fd-border bg-fd-card text-fd-foreground hover:bg-fd-accent`;
const iconTile = "grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-brand-soft text-brand";

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-brand">{children}</p>;
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="font-display mt-4 text-[2.1rem] font-semibold leading-[1.04] tracking-[-0.035em] sm:text-[2.75rem]">{title}</h2>
      <p className="mt-5 text-base leading-relaxed text-fd-muted-foreground sm:text-lg">{body}</p>
    </div>
  );
}

function CheckList({ icon: Icon, title, rows }: { icon: LucideIcon; title: string; rows: readonly [LucideIcon, string, string][] }) {
  return (
    <div className="rounded-3xl border border-fd-border bg-fd-card p-6 sm:p-8">
      <div className="flex items-center gap-3">
        <span className={iconTile}>
          <Icon className="h-5 w-5" />
        </span>
        <h3 className="font-display text-xl font-semibold tracking-[-0.02em]">{title}</h3>
      </div>
      <ul className="mt-6 divide-y divide-fd-border">
        {rows.map(([RowIcon, name, body]) => (
          <li key={name} className="flex gap-3 py-4 first:pt-0 last:pb-0">
            <RowIcon className="mt-0.5 h-4 w-4 shrink-0 text-fd-muted-foreground" />
            <div>
              <p className="font-medium">{name}</p>
              <p className="mt-1 text-sm leading-relaxed text-fd-muted-foreground">{body}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function HomeRoute({ loaderData }: Route.ComponentProps) {
  const { terminal, snippets, presets } = loaderData;
  return (
    <HomeLayout {...baseOptions()} className="min-w-0">
      <main className="w-full">
        <section className="relative overflow-hidden">
          <div className="hero-glow pointer-events-none absolute inset-0 -z-10" />
          <div className="hairline-grid pointer-events-none absolute inset-0 -z-10 opacity-35" />
          <div className={`${container} grid items-center gap-14 pb-20 pt-16 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:pb-28 lg:pt-24`}>
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-fd-border bg-fd-card/70 px-3 py-1 font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-fd-muted-foreground backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-brand" />
                Open source · MIT · Self-hosted
              </div>
              <h1 className="font-display mt-7 max-w-2xl text-[2.85rem] font-semibold leading-[1.02] tracking-[-0.045em] sm:text-6xl lg:text-[4.4rem]">
                Is a real person there, and is it them?
              </h1>
              <p className="mt-7 max-w-lg text-lg leading-relaxed text-fd-muted-foreground">
                Lumiface answers both from your own server. The oval and a screen flash on the device, two anti-spoof models
                and face matching behind an API key, and a policy per project that you tune without shipping an update.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <Link to="/docs/get-started" className={primaryButton}>
                  Run it in ten minutes
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link to="/docs/security" className={secondaryButton}>
                  What it stops
                </Link>
              </div>
              <ul className="mt-9 flex flex-wrap gap-x-6 gap-y-2 text-sm text-fd-muted-foreground">
                {["Flutter for iOS, Android and web", "React for the browser", "No faces leave your network"].map((t) => (
                  <li key={t} className="flex items-center gap-1.5">
                    <Check className="h-4 w-4 text-brand" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <LiveDemo />
          </div>
        </section>

        <section className="border-y border-fd-border bg-fd-card/50">
          <dl className={`${container} grid grid-cols-2 sm:grid-cols-4`}>
            {STATS.map(([value, label, hint], i) => (
              <div key={label} className={`py-7 sm:px-8 sm:first:pl-0 sm:last:pr-0 ${i > 0 ? "sm:border-l sm:border-fd-border" : ""}`}>
                <dd className="font-display text-4xl font-semibold tracking-[-0.04em] text-fd-foreground">{value}</dd>
                <dt className="mt-1.5 text-sm font-medium">{label}</dt>
                <p className="mt-1 font-mono text-[11px] text-fd-muted-foreground">{hint}</p>
              </div>
            ))}
          </dl>
        </section>

        <div className={container}>
          <section className="py-24 lg:py-32">
            <SectionHeading
              eyebrow="How it works"
              title="One stream, one verdict"
              body="Your backend creates the session, the device streams it, the server decides from what it received and your backend reads the answer. Every threshold is on the security page."
            />
            <FlowAnimation />
            <ol className="mt-6 grid overflow-hidden rounded-3xl border border-fd-border bg-fd-card md:grid-cols-3">
              {STEPS.map(({ icon: Icon, title, body }, i) => (
                <li key={title} className="border-b border-fd-border p-6 last:border-b-0 sm:p-8 md:border-b-0 md:border-r md:last:border-r-0">
                  <div className="flex items-center justify-between">
                    <span className={iconTile}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="font-mono text-xs text-fd-muted-foreground">0{i + 1}</span>
                  </div>
                  <h3 className="font-display mt-6 text-xl font-semibold tracking-[-0.02em]">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-fd-muted-foreground">{body}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="border-t border-fd-border py-24 lg:py-32">
            <SectionHeading
              eyebrow="Liveness"
              title="The device guides, the server decides"
              body="Nothing the device reports counts as evidence. It shows the person what to do and streams the camera; the server proves from the stream that it happened, that the frames are real and that they belong to the person in the reference photo."
            />
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              <CheckList icon={Smartphone} title="On the device — guidance only" rows={DEVICE_CHECKS} />
              <CheckList icon={Server} title="On the server — every verdict" rows={SERVER_CHECKS} />
            </div>
          </section>

          <section className="grid items-start gap-10 border-t border-fd-border py-24 lg:grid-cols-[1fr_1.1fr] lg:gap-16 lg:py-32">
            <div>
              <Eyebrow>Policy</Eyebrow>
              <h2 className="font-display mt-4 text-[2.1rem] font-semibold leading-[1.04] tracking-[-0.035em] sm:text-[2.75rem]">One policy per project</h2>
              <p className="mt-5 max-w-md text-fd-muted-foreground sm:text-lg">
                Every threshold, every timing window and every client tunable lives in a policy. Pick a preset, override what
                you need, and the next session follows it on every phone and browser; no app update, no redeploy.
              </p>
              <ul className="mt-8 space-y-4 text-sm">
                {POLICY_POINTS.map(([Icon, text]) => (
                  <li key={text} className="flex gap-3">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                    <span className="text-fd-muted-foreground">{text}</span>
                  </li>
                ))}
              </ul>
              <Link to="/docs/policy-reference" className="mt-8 inline-flex items-center gap-1.5 font-medium text-fd-foreground no-underline hover:text-brand">
                See all 43 fields
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <PresetSwitch code={presets} />
          </section>

          <section className="border-t border-fd-border py-24 lg:py-32">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <SectionHeading
                eyebrow="Custom UI"
                title="Your screen, our state machine"
                body="The default overlay takes a theme and strings. Replace the prompt, the progress, the result or the whole layer with a render prop, or drive the headless controller and draw everything yourself. The camera and the flash stay where the server needs them."
              />
              <div className="flex flex-wrap gap-3 text-sm">
                <Link to="/docs/flutter/custom-ui" className={secondaryButton}>
                  <Paintbrush className="h-4 w-4" />
                  Custom UI in Flutter
                </Link>
                <Link to="/docs/react/custom-ui" className={secondaryButton}>
                  <Paintbrush className="h-4 w-4" />
                  Custom UI in React
                </Link>
              </div>
            </div>
            <OverlayVariants snippets={snippets} />
          </section>

          <section className="border-t border-fd-border py-24 lg:py-32">
            <SectionHeading
              eyebrow="Platforms"
              title="One server, every client"
              body="The SDKs run the camera side and the oval-and-flash state machine; anything that can record a camera, or just capture JPEGs, can talk to the same API."
            />
            <div className="mt-12 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
              <div className="grid overflow-hidden rounded-3xl border border-fd-border bg-fd-card">
                {PLATFORMS.map(([Icon, name, body, href]) => (
                  <Link key={name} to={href} className="group flex items-start gap-4 border-b border-fd-border p-5 no-underline transition last:border-b-0 hover:bg-fd-accent sm:p-6">
                    <span className={iconTile}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="font-display flex items-center justify-between gap-1.5 text-lg font-semibold tracking-[-0.02em] text-fd-foreground">
                        {name}
                        <ArrowUpRight className="h-4 w-4 text-fd-muted-foreground transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-fd-foreground" />
                      </span>
                      <span className="mt-1 block text-sm text-fd-muted-foreground">{body}</span>
                    </span>
                  </Link>
                ))}
              </div>
              <div className="flex min-h-[260px] flex-col overflow-hidden rounded-3xl border border-white/10 bg-[#161722] text-[#d5d4de]">
                <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                  <span className="ml-3 font-mono text-[11px] text-white/50">terminal</span>
                </div>
                <Code hast={terminal} className="home-code flex-1 overflow-x-auto p-5 font-mono text-[12.5px] leading-6" />
              </div>
            </div>
          </section>

          <section className="border-t border-fd-border py-24 lg:py-32">
            <div className="rounded-3xl border border-amber-500/30 bg-amber-500/5 p-6 sm:p-8">
              <div className="flex items-start gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-amber-500/15 text-amber-600 dark:text-amber-400">
                  <TriangleAlert className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-display text-2xl font-semibold tracking-[-0.03em]">What it does not stop</h2>
                  <p className="mt-3 max-w-3xl leading-relaxed text-fd-muted-foreground">
                    Lumiface is not certified liveness. It stops prints, screen replays, cut-outs and paper masks; it does not stop
                    latex and silicone masks on a live person (the flow asks for no gesture) nor a real-time deepfake injected as a
                    virtual camera. The measured numbers behind every threshold are on the security page.
                  </p>
                  <Link to="/docs/security" className="mt-4 inline-flex items-center gap-1.5 font-medium text-fd-foreground no-underline hover:text-brand">
                    Read the security model
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            </div>
          </section>

          <section className="pb-24 lg:pb-32">
            <div className="relative overflow-hidden rounded-3xl border border-fd-border bg-fd-card px-6 py-16 text-center sm:px-12 sm:py-24">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_70%_at_50%_115%,color-mix(in_oklab,#6760fb_35%,transparent),transparent_70%)]" />
              <h2 className="font-display relative mx-auto max-w-2xl text-[2.4rem] font-semibold leading-[1.02] tracking-[-0.04em] sm:text-[3.5rem]">
                Run it on your own server tonight
              </h2>
              <p className="relative mx-auto mt-5 max-w-xl text-base text-fd-muted-foreground sm:text-lg">
                Clone, download the weights, start uvicorn. The Flutter example and the React demo talk to it out of the box.
              </p>
              <div className="relative mt-9 flex flex-wrap justify-center gap-3">
                <Link to="/docs/get-started" className={primaryButton}>
                  Get started
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a href={GITHUB_URL} className={secondaryButton}>
                  <Github className="h-4 w-4" />
                  GitHub
                </a>
              </div>
            </div>
          </section>
        </div>

        <footer className="border-t border-fd-border">
          <div className={`${container} flex flex-col gap-8 py-12 md:flex-row md:items-start md:justify-between`}>
            <div>
              <Logo />
              <p className="mt-3 max-w-xs text-sm text-fd-muted-foreground">Self-hosted face verification with active liveness.</p>
            </div>
            <ul className="grid grid-cols-2 gap-x-10 gap-y-2 text-sm sm:grid-cols-3">
              {FOOTER_LINKS.map(([text, href]) => (
                <li key={href}>
                  <Link to={href} className="text-fd-muted-foreground no-underline hover:text-fd-foreground">
                    {text}
                  </Link>
                </li>
              ))}
              <li>
                <a href={GITHUB_URL} className="text-fd-muted-foreground no-underline hover:text-fd-foreground">
                  GitHub
                </a>
              </li>
            </ul>
          </div>
          <div className={`${container} flex flex-wrap items-center justify-between gap-2 border-t border-fd-border py-5 font-mono text-[11px] text-fd-muted-foreground`}>
            <span>MIT license</span>
            <span>Not certified liveness. Read the security page before you rely on it.</span>
          </div>
        </footer>
      </main>
    </HomeLayout>
  );
}
