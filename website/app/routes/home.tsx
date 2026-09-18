import { HomeLayout } from "fumadocs-ui/layouts/home";
import { Link } from "react-router";
import { PresetSwitch } from "@/components/home/preset-switch";
import { LiveDemo } from "@/components/home/live-demo";
import { OverlayVariants } from "@/components/home/overlay-variants";
import { baseOptions } from "@/lib/layout.shared";

export function meta() {
  return [
    { title: "Facegate" },
    { name: "description", content: "Self-hosted face verification with active liveness for Flutter, React and any HTTP client." },
  ];
}

const DEVICE_CHECKS = [
  ["Random challenges", "Blink, smile, turn or nod, picked per session. A blink must last 40 to 600 ms."],
  ["Nose parallax", "During a turn the nose must move against the eyes; a rotated print or screen cannot do that."],
  ["Screen flash", "Three colours the server chose seconds earlier fill the screen, one frame each."],
  ["Timing", "Every step is stamped; a scripted upload or a replay answering at random times fails."],
] as const;

const SERVER_CHECKS = [
  ["Two anti-spoof gates", "MiniFASNet on every frame, then the CVPR-2024 ResNet50 on a face crop for bezel-free replays."],
  ["Flash reflection", "The cheeks must follow the colour sequence and reflect more than the wall behind."],
  ["Smile re-check", "68 landmarks confirm the smile; a latex or silicone mask passes both gates but cannot smile."],
  ["Identity", "Every frame matches the enrolled face, and every pair of frames matches each other."],
] as const;

const PLATFORMS = [
  ["Flutter", "iOS and Android with ML Kit, the web with MediaPipe, from one package."],
  ["React", "FacegateView and useFacegate on React 18 and 19, MediaPipe in the browser."],
  ["HTTP", "Any client that can open a camera talks to the same five endpoints."],
] as const;

function Ledger({ title, rows }: { title: string; rows: readonly (readonly [string, string])[] }) {
  return (
    <div>
      <h3 className="font-display text-xl font-semibold">{title}</h3>
      <dl className="mt-4 divide-y divide-fd-border border-y border-fd-border">
        {rows.map(([name, body]) => (
          <div key={name} className="grid gap-1 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
            <dt className="font-medium">{name}</dt>
            <dd className="text-sm text-fd-muted-foreground">{body}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function HomeRoute() {
  return (
    <HomeLayout {...baseOptions()} className="min-w-0">
      <main className="mx-auto w-full max-w-6xl px-4 pb-24">
        <section className="grid items-center gap-12 py-16 lg:grid-cols-[1.05fr_1fr] lg:py-24">
          <div>
            <h1 className="font-display max-w-xl text-[2.6rem] font-bold leading-[1.05] tracking-[-0.02em] sm:text-6xl">
              Is a real person there, and is it them?
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-fd-muted-foreground">
              Facegate answers both from your own server. Random challenges and a screen flash on the device, two anti-spoof
              models and face matching behind an API key, and a policy per project that you tune without shipping an update.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/docs/get-started" className="rounded-lg bg-fd-primary px-5 py-2.5 font-medium text-fd-primary-foreground no-underline hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary">
                Run it in ten minutes
              </Link>
              <Link to="/docs/security" className="rounded-lg border border-fd-border px-5 py-2.5 font-medium no-underline hover:bg-fd-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-primary">
                What it stops
              </Link>
            </div>
            <p className="mt-6 text-sm text-fd-muted-foreground">Flutter for iOS, Android and web. React for the browser. MIT, self-hosted, no faces leave your network.</p>
          </div>
          <LiveDemo />
        </section>

        <section className="grid gap-12 border-t border-fd-border py-16 lg:grid-cols-2">
          <Ledger title="On the device" rows={DEVICE_CHECKS} />
          <Ledger title="On the server" rows={SERVER_CHECKS} />
        </section>

        <section className="grid items-start gap-10 border-t border-fd-border py-16 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight">One policy per project</h2>
            <p className="mt-4 max-w-md text-fd-muted-foreground">
              Every threshold, every timing window and every client tunable lives in a policy. Pick a preset, override what
              you need, and the next session follows it on every phone and browser; no app update, no redeploy.
            </p>
            <p className="mt-4 max-w-md text-fd-muted-foreground">
              A project is an API key. Keep one for the attendance app, one for the door, one for a developer laptop that runs relaxed.
            </p>
            <Link to="/docs/policy-reference" className="mt-6 inline-block font-medium text-fd-primary">See all 55 fields</Link>
          </div>
          <PresetSwitch />
        </section>

        <section className="border-t border-fd-border py-16">
          <h2 className="font-display text-3xl font-semibold tracking-tight">Your screen, our state machine</h2>
          <p className="mt-4 max-w-2xl text-fd-muted-foreground">
            The default overlay takes a theme and strings. Replace the prompt, the progress, the result or the whole layer with a
            builder, or drive the headless controller and draw everything yourself. The camera and the flash stay where the
            server needs them.
          </p>
          <OverlayVariants />
          <div className="mt-8 flex flex-wrap gap-4 text-sm">
            <Link to="/docs/flutter/custom-ui" className="font-medium text-fd-primary">Custom UI in Flutter</Link>
            <Link to="/docs/react/custom-ui" className="font-medium text-fd-primary">Custom UI in React</Link>
          </div>
        </section>

        <section className="border-t border-fd-border py-16">
          <div className="grid gap-8 sm:grid-cols-3">
            {PLATFORMS.map(([name, body]) => (
              <div key={name}>
                <h3 className="font-display text-xl font-semibold">{name}</h3>
                <p className="mt-2 text-sm text-fd-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
          <pre className="mt-10 overflow-x-auto rounded-xl border border-fd-border bg-fd-card p-4 font-mono text-[12.5px] leading-6">
            <code>{`cd server && uv sync && uv run python weights/download.py && cp .env.example .env
uv run uvicorn app.main:app --port 8000

curl -X POST localhost:8000/v1/subjects -H "X-API-Key: change-me" -F external_id=E001 -F photo=@me.jpg
flutter run -d chrome      # packages/facegate/example
bun run dev:react          # packages/facegate-react/demo`}</code>
          </pre>
        </section>

        <section className="border-t border-fd-border py-16">
          <h2 className="font-display text-3xl font-semibold tracking-tight">What it does not stop</h2>
          <p className="mt-4 max-w-2xl text-fd-muted-foreground">
            Facegate is not certified liveness. It stops prints, screen replays, cut-outs and paper masks; it stops latex and
            silicone masks only through the smile challenge; it does not stop a real-time deepfake injected as a virtual camera.
            The measured numbers behind every threshold are on the security page.
          </p>
          <Link to="/docs/security" className="mt-6 inline-block font-medium text-fd-primary">Read the security model</Link>
        </section>
      </main>
    </HomeLayout>
  );
}
