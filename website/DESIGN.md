# Lumiface design system

Adapted from the frame.io capture on Inspo (https://inspomcp.dev/d/frame-io/DESIGN.md), 2026-09-18. Dark first, monochrome surfaces, one cobalt accent that lands on labels, icons and selection states rather than buttons.

## Colors

Tokens live in `app/app.css` as fumadocs `--color-fd-*` overrides plus `--brand`.

| Role | Dark | Light |
|---|---|---|
| background | `#0d0d18` | `#f5f5f8` |
| card / muted | `#161722` | `#fcfcfc` / `#e8e9f3` |
| popover | `#1d1f2c` | `#fcfcfc` |
| foreground | `#f5f5f8` | `#0d0d18` |
| muted foreground | `rgba(213,214,234,.64)` | `#5c5d75` |
| border | `rgba(213,214,234,.11)` | `rgba(46,47,64,.14)` |
| primary (buttons) | `#f5f5f8` on `#0d0d18` | `#0d0d18` on `#fcfcfc` |
| brand (accent) | `#8f8bff` | `#4f47e6` |
| brand-soft | `rgba(103,96,251,.18)` | `rgba(103,96,251,.12)` |
| logo tile | `#6760fb` | `#6760fb` |

Success stays emerald, failure red, warnings amber.

## Typography

- Display: Inter Tight 600, tracking -0.035em to -0.045em, line-height 1.02 to 1.04. h1 ≈ 70px desktop / 46px phone, h2 ≈ 44px / 34px.
- Body: Inter 400/500, 16 to 18px, line-height 1.6.
- Eyebrows and metadata: JetBrains Mono 11 to 12px, uppercase, tracking 0.08em, brand colour.

## Shape and spacing

- Radius: 10px for icon tiles and small code blocks, 24px (`rounded-3xl`) for cards and windows, pills for buttons and tabs.
- Flat surfaces: hairline borders, no drop shadows except the phone mock-ups.
- Section rhythm: 96px on desktop (`py-24`), 128px on large screens (`py-32`), hairline `border-t` between sections.
- Container: 1280px (`max-w-7xl`), 20px gutter on phones, 32px from `sm`.

## Logo

Wordmark only: "Lumiface" set in Inter Tight 600 with -0.035em tracking and a cobalt full stop, converted to paths so it renders the same everywhere. `app/components/logo.tsx` inlines it with `currentColor`; README uses `docs/images/logo-light.svg` and `logo-dark.svg` through `<picture>`; favicon `public/icon.svg` is an "L" monogram on the cobalt tile. Regenerate from Inter Tight with fontTools if the wordmark changes.
