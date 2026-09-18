import { DEFAULT_THEME, FaceGuide, type FacegateTheme } from "@facegate/react";

const VARIANTS: { title: string; prompt: string; phase: "challenge" | "success"; theme: FacegateTheme }[] = [
  { title: "Default theme", prompt: "Smile", phase: "challenge", theme: DEFAULT_THEME },
  { title: "Rounded guide, brand colours", prompt: "Welcome back", phase: "success", theme: { ...DEFAULT_THEME, guideShape: "roundedRect", guideActive: "#2dd4bf", guideSuccess: "#2dd4bf", guide: "#a7f3d0", guideWidthFraction: 0.8, guideAspectRatio: 1.2 } },
  { title: "No guide, your own overlay", prompt: "Turn your head left", phase: "challenge", theme: { ...DEFAULT_THEME, guideShape: "none", mask: "transparent" } },
];

/** The real FaceGuide from the React SDK over an empty camera surface, one theme each. */
export function OverlayVariants() {
  return (
    <div className="mt-10 grid gap-8 sm:grid-cols-3">
      {VARIANTS.map(({ title, prompt, phase, theme }) => (
        <figure key={title} className="text-center">
          <div className="relative mx-auto aspect-[9/17] w-full max-w-[200px] overflow-hidden rounded-[1.6rem] border border-fd-border bg-[#1a2129]">
            <FaceGuide theme={theme} phase={phase} />
            <div className="absolute inset-x-0 top-0 flex justify-center gap-1.5 pt-4">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-1 w-5 rounded-full" style={{ background: i === 0 || phase === "success" ? theme.progress : theme.progressBackground }} />
              ))}
            </div>
            <div className="absolute inset-x-0 bottom-0 pb-7 text-center text-[15px] font-semibold text-white">{prompt}</div>
          </div>
          <figcaption className="mt-3 text-sm text-fd-muted-foreground">{title}</figcaption>
        </figure>
      ))}
    </div>
  );
}
