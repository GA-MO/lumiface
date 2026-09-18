import { useState } from "react";

const PRESETS: Record<string, { summary: string; overrides: Record<string, unknown> }> = {
  balanced: { summary: "Calibrated defaults from the environment. Phone-tested attendance check-in.", overrides: {} },
  strict: {
    summary: "Higher match and anti-spoof bars, three challenges, commanded turn direction. Access control, KYC.",
    overrides: { match_threshold: 0.55, spoof_threshold: 0.6, spoof_hard_floor: 0.35, cvpr_threshold: 0.4, challenge_count: 3, flash_min_correlation: 0.7, turn_strict_direction: true, client: { parallax_min_shift: 0.1, smile_threshold: 0.8 } },
  },
  relaxed: {
    summary: "Lower bars, flash and smile checks record scores only. Low-risk flows, poor lighting, kiosks.",
    overrides: { match_threshold: 0.4, spoof_hard_floor: 0.2, cvpr_threshold: 0.2, flash_enforce: false, smile_enforce: false, max_challenge_ms: 8000, client: { challenge_timeout_ms: 15000, face_lost_grace_ms: 2500 } },
  },
  emulator: {
    summary: "Flash off and smaller faces accepted. Android emulator with a webcam, CI demos.",
    overrides: { flash_enforce: false, spoof_hard_floor: 0.2, min_face_size: 60, client: { min_face_width_fraction: 0.2 } },
  },
};

export function PresetSwitch() {
  const [preset, setPreset] = useState("strict");
  const body = JSON.stringify({ preset, overrides: PRESETS[preset].overrides }, null, 2);
  return (
    <div className="overflow-hidden rounded-xl border border-fd-border bg-fd-card">
      <div className="flex flex-wrap gap-1 border-b border-fd-border p-2" role="tablist" aria-label="Preset">
        {Object.keys(PRESETS).map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={preset === name}
            onClick={() => setPreset(name)}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-fd-muted-foreground transition-colors aria-selected:bg-fd-primary/10 aria-selected:text-fd-primary hover:text-fd-foreground focus-visible:outline-2 focus-visible:outline-fd-primary"
          >
            {name}
          </button>
        ))}
      </div>
      <p className="px-4 pt-3 text-sm text-fd-muted-foreground">{PRESETS[preset].summary}</p>
      <pre className="overflow-x-auto p-4 font-mono text-[12.5px] leading-6"><code>{`PUT /v1/policy\n${body}`}</code></pre>
    </div>
  );
}
