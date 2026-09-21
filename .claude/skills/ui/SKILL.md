---
name: ui
description: Fix one visual thing the user saw — locate the exact element in the running page first, change it with design-system tokens only, screenshot before/after at the same viewport. Use for "spacing/size/colour/alignment looks wrong" requests, with or without a screenshot. User-invoked only.
disable-model-invocation: true
argument-hint: "<สิ่งที่เห็นว่าผิด> [หน้า/URL] [+ รูป]"
---

# /ui — look, point, change, look again

`$ARGUMENTS` describes what looks wrong, often with a screenshot. The failure this skill exists to
prevent: changing the wrong element, or the right element with a made-up value, and reporting done
without looking. Everything here is mechanical; the only judgement (which token) is stated before it is applied.

## 1. Open the real page at the user's viewport

Find the dev server (`.claude/ship.md` ports, then 3000–3003, 5173, 6006). If none answers, start
the project's dev command in the background and remember to stop it in step 5.
Open the page in chrome-devtools. If the user sent a screenshot, match its width (phone ≈ 375–430,
tablet ≈ 768–1024, desktop ≈ 1280+; read it from the image). Take the **before** screenshot into a
path under the project's ignored scratch dir (`.claude/ui-shots/`, create it and add to .git/info/exclude) and keep it.
If chrome-devtools cannot attach (profile held by another session), try claude-in-chrome; if that fails too,
continue but start the report with `ไม่ได้ดูด้วยตา:` and replace `viewport <w> ✓` with what you actually checked.

## 2. Point at the element before touching anything

Use the DOM (take_snapshot / evaluate_script), not the words, to find the element the user means:
the thing that visibly has the problem in the screenshot, not its nearest container. Read its
computed style for the property in question.

Print this one line as plain text **in its own turn, before any Edit/Write/sed call** (never inside
the final report, never in the same turn as the edit), then continue without waiting:

    จะเปลี่ยน <property> ของ <selector / component file:line> จาก <current> เป็น <token> (<value>)

If two elements could be meant and the fix differs, show both in the same line and pick the one
the screenshot points at. Never widen the change to siblings "for consistency" unless asked.

## 3. Change it with the design system only

- Tokens or scale utilities only (`gap-4`, `pt-17.5`, `var(--space-4)`), never arbitrary values
  (`p-[13px]`, `text-[0.9375rem]`). If no token fits, use the nearest one and say so; do not invent.
- Reuse the primitive that already exists (Button, Card, Modal…) rather than styling around it.
- Touch the one file the element lives in. No refactor, no comment, no new component.
- If the fix belongs in the shared component (the same wrong spacing appears on every card), say
  that in the report and fix it there once — that is the one case where more than one place changes.

## 4. Look again

Screenshot **after** at the same viewport. If the change is layout (spacing, size, wrap), also
375px and 1280px. Compare with the before shot yourself: did the thing the user pointed at change,
and did nothing else move? If something else moved, fix or revert before reporting.

## 5. Report

    ui: <property> <element> <before → after (token)> · file:line · viewport <w> ✓ [375 ✓ 1280 ✓] · shots: <before path> <after path>

The report line is the last message: no notes after it (a shared-component side effect goes in the
same line as `shared: <n> pages`). Do not delete the screenshots. Stop any dev server you started. Then stop.
