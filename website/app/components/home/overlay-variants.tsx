import { DEFAULT_THEME, FaceGuide, type LumifaceTheme } from "@lumiface/react";
import { Code } from "@/components/code";
import type { HastNode } from "@/lib/code.server";

const BRAND: LumifaceTheme = {
  ...DEFAULT_THEME,
  guideShape: "roundedRect",
  guide: "#a7f3d0",
  guideActive: "#2dd4bf",
  guideSuccess: "#2dd4bf",
  guideWidthFraction: 0.78,
  guideAspectRatio: 1.25,
  mask: "rgba(4,20,24,0.6)",
};

function CameraFrame({ src, position }: { src: string; position: string }) {
  return <img src={`${import.meta.env.BASE_URL}people/${src}`} alt="" className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition: position }} />;
}

function StatusBar() {
  return (
    <div className="absolute inset-x-0 top-0 flex items-center justify-between px-5 pt-2.5 text-[10px] font-semibold text-white/90" aria-hidden>
      <span>9:41</span>
      <span className="h-[18px] w-[64px] rounded-full bg-black" />
      <span className="flex items-center gap-1">
        <span className="flex items-end gap-px">
          {[3, 5, 7, 9].map((h) => (
            <span key={h} className="w-[3px] rounded-sm bg-white" style={{ height: h }} />
          ))}
        </span>
        <span className="ml-0.5 h-[9px] w-[18px] rounded-[3px] border border-white/70 p-px">
          <span className="block h-full w-3/4 rounded-[1px] bg-white" />
        </span>
      </span>
    </div>
  );
}

function StepDots({ done, total, color, track }: { done: number; total: number; color: string; track: string }) {
  return (
    <div className="absolute inset-x-0 top-10 flex justify-center gap-1.5" aria-hidden>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className="h-1 w-6 rounded-full" style={{ background: i < done ? color : track }} />
      ))}
    </div>
  );
}

function Phone({ photo, position, children }: { photo: string; position: string; children: React.ReactNode }) {
  return (
    <div className="relative mx-auto aspect-[9/19] w-full max-w-[220px] rounded-[2.4rem] border-[6px] border-[#1d1f2c] bg-[#1d1f2c] shadow-[0_40px_70px_-30px_rgba(0,0,0,0.7)] ring-1 ring-white/10">
      <div className="absolute -left-[7px] top-24 h-9 w-[3px] rounded-l bg-[#2a3440]" />
      <div className="absolute -left-[7px] top-36 h-9 w-[3px] rounded-l bg-[#2a3440]" />
      <div className="absolute -right-[7px] top-28 h-14 w-[3px] rounded-r bg-[#2a3440]" />
      <div className="relative h-full w-full overflow-hidden rounded-[1.9rem] bg-[#0d0d18]">
        <CameraFrame src={photo} position={position} />
        <div className="absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/45 to-transparent" />
        {children}
        <StatusBar />
      </div>
    </div>
  );
}

function Prompt({ children, color = "#fff" }: { children: React.ReactNode; color?: string }) {
  return (
    <div className="absolute inset-x-0 bottom-0 pb-8 text-center text-[15px] font-semibold" style={{ color }}>
      {children}
    </div>
  );
}

function CustomOverlay() {
  const accent = "#ffab40";
  return (
    <div className="absolute inset-0">
      <div className="absolute rounded-2xl border-[3px]" style={{ left: "18%", top: "15%", width: "62%", height: "46%", borderColor: accent }}>
        <span className="absolute -top-2 left-3 rounded bg-black/70 px-1.5 py-px text-[8px] font-semibold uppercase tracking-wide" style={{ color: accent }}>
          face 0.94
        </span>
      </div>
      <div className="absolute inset-x-3 bottom-3 rounded-2xl bg-black/80 p-3 text-center backdrop-blur">
        <div className="text-[14px] font-bold" style={{ color: accent }}>
          Move closer until your face fills the oval
        </div>
        <div className="mt-1.5 flex items-center justify-center gap-1.5">
          {[1, 2].map((n) => (
            <span
              key={n}
              className="grid h-4 w-4 place-items-center rounded-full text-[8px] font-bold"
              style={{ background: n === 1 ? accent : "rgba(255,255,255,0.15)", color: n === 1 ? "#000" : "#fff" }}
            >
              {n}
            </span>
          ))}
          <span className="ml-1 text-[9px] text-white/60">step 1 of 2</span>
        </div>
      </div>
    </div>
  );
}

export const OVERLAY_SNIPPETS = [
  `<LumifaceView
  client={client}
  sessionProvider={session}
  strings={TH}
/>`,
  `<LumifaceView
  theme={{
    guideShape: "roundedRect",
    guideActive: "#2dd4bf",
    guideSuccess: "#2dd4bf",
  }}
/>`,
  `<LumifaceView
  renderOverlay={(s) => (
    <MyOverlay
      box={s.displayBox}
      message={s.message}
    />
  )}
/>`,
];

const VARIANTS = [
  {
    title: "Default overlay",
    photo: "smile.jpg",
    position: "50% 30%",
    body: "Oval guide, progress bar and prompt come from the theme and strings. Nothing to write.",
    tag: "theme + strings",
    screen: (
      <>
        <FaceGuide theme={DEFAULT_THEME} phase="challenge" />
        <StepDots done={1} total={2} color={DEFAULT_THEME.progress} track={DEFAULT_THEME.progressBackground} />
        <Prompt>Move closer until your face fills the oval</Prompt>
      </>
    ),
  },
  {
    title: "Your brand",
    photo: "welcome.jpg",
    position: "50% 25%",
    body: "Change the guide shape, the colours and the mask; the state machine stays the same.",
    tag: "theme={...}",
    screen: (
      <>
        <FaceGuide theme={BRAND} phase="success" />
        <StepDots done={2} total={2} color="#2dd4bf" track="rgba(255,255,255,0.25)" />
        <Prompt color="#2dd4bf">Welcome back, Nan</Prompt>
      </>
    ),
  },
  {
    title: "Your own overlay",
    photo: "turn.jpg",
    position: "50% 30%",
    body: "renderOverlay gets the face box, the phase and the message; draw whatever your product needs.",
    tag: "renderOverlay",
    screen: <CustomOverlay />,
  },
];

/** Three phones running the real FaceGuide from the React SDK over a still camera frame. */
export function OverlayVariants({ snippets }: { snippets: HastNode[] }) {
  return (
    <div className="mt-12 grid gap-10 sm:grid-cols-3 sm:gap-6">
      {VARIANTS.map(({ title, body, tag, photo, position, screen }, i) => (
        <figure key={title} className="flex flex-col">
          <Phone photo={photo} position={position}>
            {screen}
          </Phone>
          <figcaption className="mt-6">
            <div className="flex items-center gap-2">
              <h3 className="font-display text-base font-semibold">{title}</h3>
              <code className="rounded-md bg-brand-soft px-1.5 py-0.5 font-mono text-[11px] text-brand">{tag}</code>
            </div>
            <p className="mt-1.5 text-sm text-fd-muted-foreground">{body}</p>
          </figcaption>
          <Code hast={snippets[i]} className="home-code mt-3 overflow-x-auto rounded-[10px] border border-fd-border bg-fd-card p-3 font-mono text-[11.5px] leading-5" />
        </figure>
      ))}
    </div>
  );
}
