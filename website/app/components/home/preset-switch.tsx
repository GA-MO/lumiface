import { useState } from "react";
import { Code } from "@/components/code";
import type { HastNode } from "@/lib/code.server";

export const PRESETS: Record<string, { summary: string; when: string; overrides: Record<string, unknown> }> = {
  balanced: { summary: "Calibrated defaults from the environment.", when: "Phone-tested attendance check-in", overrides: {} },
  strict: {
    summary: "Higher match and anti-spoof bars, a longer walk into a fuller oval, tighter flash correlation.",
    when: "Access control, KYC",
    overrides: { match_threshold: 0.55, spoof_threshold: 0.6, spoof_hard_floor: 0.35, cvpr_threshold: 0.4, move_min_growth: 1.4, flash_min_correlation: 0.7, client: { oval_min_fill: 0.9, move_start_max_ratio: 0.5 } },
  },
  relaxed: {
    summary: "Lower bars; the flash records scores only, more time for the oval.",
    when: "Low-risk flows, poor lighting, kiosks",
    overrides: { match_threshold: 0.4, spoof_hard_floor: 0.2, cvpr_threshold: 0.2, flash_enforce: false, max_challenge_ms: 15000, client: { challenge_timeout_ms: 15000, face_lost_grace_ms: 2500, min_face_width_fraction: 0.2 } },
  },
  emulator: {
    summary: "Flash off and smaller faces accepted.",
    when: "Android emulator with a webcam, CI demos",
    overrides: { flash_enforce: false, spoof_hard_floor: 0.2, min_face_size: 60, client: { min_face_width_fraction: 0.2 } },
  },
};

export function presetBody(preset: string) {
  return JSON.stringify({ preset, overrides: PRESETS[preset].overrides }, null, 2);
}

export function PresetSwitch({ code }: { code: Record<string, HastNode> }) {
  const [preset, setPreset] = useState("strict");
  const current = PRESETS[preset];
  return (
    <div className="overflow-hidden rounded-3xl border border-fd-border bg-fd-card">
      <div className="flex flex-col gap-3 border-b border-fd-border p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="inline-flex rounded-full bg-fd-muted p-1" role="tablist" aria-label="Preset">
          {Object.keys(PRESETS).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={preset === name}
              onClick={() => setPreset(name)}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-fd-muted-foreground transition-colors hover:text-fd-foreground aria-selected:bg-fd-background aria-selected:text-fd-foreground aria-selected:shadow-sm focus-visible:outline-2 focus-visible:outline-fd-ring"
            >
              {name}
            </button>
          ))}
        </div>
        <span className="hidden font-mono text-[11px] text-fd-muted-foreground sm:block">PUT /v1/policy</span>
      </div>
      <div className="border-b border-fd-border px-4 py-3">
        <p className="text-sm">{current.summary}</p>
        <p className="mt-0.5 text-xs text-fd-muted-foreground">For: {current.when}</p>
      </div>
      <Code hast={code[preset]} className="home-code overflow-x-auto bg-fd-muted/40 p-4 font-mono text-[12.5px] leading-6" />
    </div>
  );
}
