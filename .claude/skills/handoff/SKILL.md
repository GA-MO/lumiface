---
name: handoff
description: Pause a multi-session feature — write what is done, open, and discovered into the plan file so a fresh session can continue from the file alone. Use before /ship at the end of a phase, or when context is getting full. User-invoked only.
disable-model-invocation: true
argument-hint: "[docs/plans/<file>.md]"
---

# /handoff — leave the next session everything it needs, in the file

The user works in phases across sessions. Memory between sessions is the plan file, not
/compact and not your memory directory. Write it so an agent with **only this file and `git log`**
can continue.

## 1. Find the plan file

`$ARGUMENTS` if given. Otherwise the plan file this session's brief referenced; otherwise the
most recently modified `docs/plans/*.md`. If none exists, create `docs/plans/<feature>.md` with a
one-paragraph goal and the phases you can infer from this session, then continue.

## 2. Update it — replace, don't append a diary

Keep the file short. Edit these sections in place (create them if missing):

    ## สถานะ (updated <date>)
    ทำแล้ว: <phase/items done, one line each, with the commit or file that proves it>
    ค้าง: <what is unfinished in the current phase, concretely — which file, which state, which case>
    ค้นพบ: <what turned out different from the plan: a wrong assumption, an API that lies, a dependency>
    ถัดไป: /go phase <n> ตาม docs/plans/<file>.md   ← always this shape. Current phase done → point at the next phase.
           No phase left → `/go ตรวจ <what is not yet proven> ตาม docs/plans/<file>.md`; `/ship` belongs in your report line, never here.

- "ค้าง" and "ค้นพบ" are the only parts that matter; spend the words there.
- If a later phase is now wrong because of what you found, edit that phase, and say so in one line under ค้นพบ.
- No progress narrative, no praise, no "next steps" beyond the one command. Whole section under 15 lines.

## 3. Leave the tree honest

Uncommitted work stays uncommitted (the user will `/ship`). Do **not** run the test suite or a build to find out the state — this skill runs when context is nearly full; write from what this session already saw. If you do not know whether the tree builds, write under ค้าง: `ยังไม่ได้พิสูจน์: <command>`. If there is a half-done change that
would break the build, say so in ค้าง and name the file. Stop any dev server you started.

## 4. Report — two lines

    handoff → docs/plans/<file>.md (ค้าง: <n> items · ค้นพบ: <n>)
    next: /go phase <n> ตาม docs/plans/<file>.md

Flush left, no leading spaces, no code fence. Then stop. Do not /ship on your own.
