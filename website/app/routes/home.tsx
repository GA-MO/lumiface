import { HomeLayout } from "fumadocs-ui/layouts/home";
import {
  ArrowRight,
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

curl -X POST localhost:8000/v1/subjects -H "X-API-Key: change-me" \\
  -F external_id=E001 -F photo=@me.jpg

flutter run -d chrome      # packages/facegate/example
bun run dev:react          # packages/facegate-react/demo`;

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
    { title: "Facegate" },
    { name: "description", content: "Self-hosted face verification with active liveness for Flutter, React and any HTTP client." },
  ];
}

const STATS = [
  ["2", "anti-spoof models", "MiniFASNet + CVPR-2024"],
  ["4", "device challenges", "blink, smile, turn, nod"],
  ["55", "policy fields", "tuned per project, no redeploy"],
  ["5", "HTTP endpoints", "enrol, session, verify, policy, health"],
] as const;

const STEPS = [
  { icon: KeyRound, title: "Enrol once", body: "POST a photo per subject behind your project's API key. The embedding stays on your server." },
  { icon: ScanFace, title: "Challenge on the device", body: "The SDK opens the camera, picks random challenges and flashes three server-chosen colours." },
  { icon: ShieldCheck, title: "Verify on the server", body: "Two anti-spoof gates, flash reflection, smile re-check and identity match return one result with reason codes." },
] as const;

const DEVICE_CHECKS: readonly [LucideIcon, string, string][] = [
  [Sparkles, "Random challenges", "Blink, smile, turn or nod, picked per session. A blink must last 40 to 600 ms."],
  [Eye, "Nose parallax", "During a turn the nose must move against the eyes; a rotated print or screen cannot do that."],
  [Zap, "Screen flash", "Three colours the server chose seconds earlier fill the screen, one frame each."],
  [Timer, "Timing", "Every step is stamped; a scripted upload or a replay answering at random times fails."],
];

const SERVER_CHECKS: readonly [LucideIcon, string, string][] = [
  [ShieldCheck, "Two anti-spoof gates", "MiniFASNet on every frame, then the CVPR-2024 ResNet50 on a face crop for bezel-free replays."],
  [Zap, "Flash reflection", "The cheeks must follow the colour sequence and reflect more than the wall behind."],
  [ScanFace, "Smile re-check", "68 landmarks confirm the smile; a latex or silicone mask passes both gates but cannot smile."],
  [KeyRound, "Identity", "Every frame matches the enrolled face, and every pair of frames matches each other."],
];

const POLICY_POINTS: readonly [LucideIcon, string][] = [
  [SlidersHorizontal, "A project is an API key: one for the attendance app, one for the door, one for a laptop that runs relaxed."],
  [Layers, "Presets for balanced, strict, relaxed and emulator; overrides win field by field."],
  [Zap, "The session carries the client tunables, so the SDK follows the policy without a rebuild."],
];

const PLATFORMS: readonly [LucideIcon, string, string, string][] = [
  [Smartphone, "Flutter", "iOS and Android with ML Kit, the web with MediaPipe, from one package.", "/docs/flutter"],
  [Code2, "React", "FacegateView and useFacegate on React 18 and 19, MediaPipe in the browser.", "/docs/react"],
  [Globe, "HTTP", "Any client that can open a camera talks to the same five endpoints.", "/docs/api"],
];

const primaryButton =
  "inline-flex items-center gap-2 rounded-lg bg-fd-primary px-5 py-2.5 font-medium text-fd-primary-foreground no-underline shadow-sm transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary";
const secondaryButton =
  "inline-flex items-center gap-2 rounded-lg border border-fd-border bg-fd-background px-5 py-2.5 font-medium no-underline transition hover:bg-fd-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary";

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-[0.14em] text-fd-primary">{children}</p>;
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="font-display mt-3 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-relaxed text-fd-muted-foreground sm:text-lg">{body}</p>
    </div>
  );
}

function CheckList({ icon: Icon, title, rows }: { icon: LucideIcon; title: string; rows: readonly [LucideIcon, string, string][] }) {
  return (
    <div className="rounded-2xl border border-fd-border bg-fd-card p-6 shadow-sm sm:p-8">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-fd-primary/10 text-fd-primary">
          <Icon className="h-5 w-5" />
        </span>
        <h3 className="font-display text-xl font-semibold">{title}</h3>
      </div>
      <ul className="mt-6 space-y-5">
        {rows.map(([RowIcon, name, body]) => (
          <li key={name} className="flex gap-3">
            <RowIcon className="mt-0.5 h-4 w-4 shrink-0 text-fd-muted-foreground" />
            <div>
              <p className="font-medium">{name}</p>
              <p className="mt-0.5 text-sm leading-relaxed text-fd-muted-foreground">{body}</p>
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
          <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,color-mix(in_oklab,var(--color-fd-primary)_22%,transparent),transparent)]" />
          <div className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(to_right,var(--color-fd-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-fd-border)_1px,transparent_1px)] bg-[size:48px_48px] opacity-40 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_20%,transparent_80%)]" />
          <div className="mx-auto grid w-full max-w-6xl items-center gap-12 px-4 pb-20 pt-16 lg:grid-cols-[1.05fr_1fr] lg:pb-28 lg:pt-24">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-fd-border bg-fd-background/80 px-3 py-1 text-xs font-medium text-fd-muted-foreground shadow-sm backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-fd-primary" />
                Open source · MIT · Self-hosted
              </div>
              <h1 className="font-display mt-6 max-w-xl text-[2.6rem] font-extrabold leading-[1.05] tracking-[-0.02em] sm:text-6xl">
                Is a real person there, and is it them?
              </h1>
              <p className="mt-6 max-w-lg text-lg leading-relaxed text-fd-muted-foreground">
                Facegate answers both from your own server. Random challenges and a screen flash on the device, two anti-spoof
                models and face matching behind an API key, and a policy per project that you tune without shipping an update.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/docs/get-started" className={primaryButton}>
                  Run it in ten minutes
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link to="/docs/security" className={secondaryButton}>
                  What it stops
                </Link>
              </div>
              <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-fd-muted-foreground">
                {["Flutter for iOS, Android and web", "React for the browser", "No faces leave your network"].map((t) => (
                  <li key={t} className="flex items-center gap-1.5">
                    <Check className="h-4 w-4 text-fd-primary" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <LiveDemo />
          </div>
        </section>

        <section className="border-y border-fd-border bg-fd-card/60">
          <dl className="mx-auto grid w-full max-w-6xl grid-cols-2 divide-fd-border px-4 sm:grid-cols-4 sm:divide-x">
            {STATS.map(([value, label, hint]) => (
              <div key={label} className="py-6 sm:px-6 sm:first:pl-0 sm:last:pr-0">
                <dd className="font-display text-3xl font-bold tracking-tight text-fd-foreground">{value}</dd>
                <dt className="mt-1 text-sm font-medium">{label}</dt>
                <p className="mt-0.5 text-xs text-fd-muted-foreground">{hint}</p>
              </div>
            ))}
          </dl>
        </section>

        <div className="mx-auto w-full max-w-6xl px-4">
          <section className="py-20">
            <SectionHeading
              eyebrow="How it works"
              title="Three calls, one result"
              body="Enrol a face, run a session on the device, verify on the server. Every step is stamped and every threshold is on the security page."
            />
            <FlowAnimation />
            <ol className="mt-8 grid gap-6 md:grid-cols-3">
              {STEPS.map(({ icon: Icon, title, body }, i) => (
                <li key={title} className="relative rounded-2xl border border-fd-border bg-fd-card p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-fd-primary/10 text-fd-primary">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="font-mono text-xs text-fd-muted-foreground">0{i + 1}</span>
                  </div>
                  <h3 className="font-display mt-5 text-lg font-semibold">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-fd-muted-foreground">{body}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="border-t border-fd-border py-20">
            <SectionHeading
              eyebrow="Liveness"
              title="Checks on both sides of the wire"
              body="The device proves a live person is in front of the camera; the server proves the frames are real and belong to the enrolled subject."
            />
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              <CheckList icon={Smartphone} title="On the device" rows={DEVICE_CHECKS} />
              <CheckList icon={Server} title="On the server" rows={SERVER_CHECKS} />
            </div>
          </section>

          <section className="grid items-start gap-10 border-t border-fd-border py-20 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
            <div>
              <Eyebrow>Policy</Eyebrow>
              <h2 className="font-display mt-3 text-3xl font-bold tracking-tight sm:text-4xl">One policy per project</h2>
              <p className="mt-4 max-w-md text-fd-muted-foreground">
                Every threshold, every timing window and every client tunable lives in a policy. Pick a preset, override what
                you need, and the next session follows it on every phone and browser; no app update, no redeploy.
              </p>
              <ul className="mt-6 space-y-3 text-sm">
                {POLICY_POINTS.map(([Icon, text]) => (
                  <li key={text} className="flex gap-3">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-fd-primary" />
                    <span className="text-fd-muted-foreground">{text}</span>
                  </li>
                ))}
              </ul>
              <Link to="/docs/policy-reference" className="mt-8 inline-flex items-center gap-1.5 font-medium text-fd-primary no-underline hover:underline">
                See all 55 fields
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <PresetSwitch code={presets} />
          </section>

          <section className="border-t border-fd-border py-20">
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

          <section className="border-t border-fd-border py-20">
            <SectionHeading
              eyebrow="Platforms"
              title="One server, every client"
              body="The SDKs run the camera side and the challenge state machine; anything that can capture JPEGs can talk to the same API."
            />
            <div className="mt-12 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
              <div className="grid gap-4">
                {PLATFORMS.map(([Icon, name, body, href]) => (
                  <Link key={name} to={href} className="group flex items-start gap-4 rounded-2xl border border-fd-border bg-fd-card p-5 no-underline shadow-sm transition hover:border-fd-primary/50">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-fd-primary/10 text-fd-primary">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span>
                      <span className="font-display flex items-center gap-1.5 text-base font-semibold text-fd-foreground">
                        {name}
                        <ArrowRight className="h-4 w-4 opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
                      </span>
                      <span className="mt-1 block text-sm text-fd-muted-foreground">{body}</span>
                    </span>
                  </Link>
                ))}
              </div>
              <div className="flex min-h-[260px] flex-col overflow-hidden rounded-2xl border border-fd-border bg-[#0f141c] shadow-lg">
                <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                  <span className="ml-3 font-mono text-[11px] text-white/50">terminal</span>
                </div>
                <Code hast={terminal} className="home-code flex-1 overflow-x-auto p-5 font-mono text-[12.5px] leading-6 text-[#d6dee8]" />
              </div>
            </div>
          </section>

          <section className="border-t border-fd-border py-20">
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6 sm:p-8">
              <div className="flex items-start gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400">
                  <TriangleAlert className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="font-display text-2xl font-bold tracking-tight">What it does not stop</h2>
                  <p className="mt-3 max-w-3xl leading-relaxed text-fd-muted-foreground">
                    Facegate is not certified liveness. It stops prints, screen replays, cut-outs and paper masks; it stops latex
                    and silicone masks only through the smile challenge; it does not stop a real-time deepfake injected as a
                    virtual camera. The measured numbers behind every threshold are on the security page.
                  </p>
                  <Link to="/docs/security" className="mt-4 inline-flex items-center gap-1.5 font-medium text-fd-primary no-underline hover:underline">
                    Read the security model
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            </div>
          </section>

          <section className="pb-24">
            <div className="relative overflow-hidden rounded-3xl bg-fd-primary px-6 py-14 text-center text-fd-primary-foreground sm:px-12">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_80%_at_50%_120%,rgba(255,255,255,0.25),transparent)]" />
              <h2 className="font-display relative text-3xl font-bold tracking-tight sm:text-4xl">Run it on your own server tonight</h2>
              <p className="relative mx-auto mt-4 max-w-xl text-base opacity-90 sm:text-lg">
                Clone, download the weights, start uvicorn. The Flutter example and the React demo talk to it out of the box.
              </p>
              <div className="relative mt-8 flex flex-wrap justify-center gap-3">
                <Link to="/docs/get-started" className="inline-flex items-center gap-2 rounded-lg bg-fd-primary-foreground px-5 py-2.5 font-medium text-fd-primary no-underline shadow-sm transition hover:opacity-90">
                  Get started
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a href={GITHUB_URL} className="inline-flex items-center gap-2 rounded-lg border border-white/30 px-5 py-2.5 font-medium text-fd-primary-foreground no-underline transition hover:bg-white/10">
                  <Github className="h-4 w-4" />
                  GitHub
                </a>
              </div>
            </div>
          </section>
        </div>
      </main>
    </HomeLayout>
  );
}
