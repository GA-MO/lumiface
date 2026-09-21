---
name: go
description: Turn a rough one-line ask into a 4-line brief (goal / references / don'ts / done-when), get one "ทำ" from the user, then finish the whole task without stopping. User-invoked only.
disable-model-invocation: true
argument-hint: "[!] <งานที่จะทำ พิมพ์หยาบๆ ได้>"
---

# /go — brief first, then finish

The user types tasks in one short line and decides along the way. Your job is to do the
front-loading they will not do: turn `$ARGUMENTS` into a brief, get one confirmation, then run to the end.

## 1. Draft the brief (read before you write)

Look at CLAUDE.md, `git log -10 --format=%s`, and the files the ask obviously touches. Then write
exactly this, in Thai, each line one sentence:

    เป้าหมาย: <what the user can do afterwards that they cannot now>
    อ้างอิง: <existing component / page / doc / figma / storybook to copy from — real paths>
    ห้าม: <files not to touch, deps not to add, things not to write (tests, comments, new primitives)>
    เสร็จเมื่อ: <a check YOU can run: a URL at a width, a story, a command — never "works correctly">

Put `[เดา]` right next to the thing you guessed ("อ้างอิง: components/Card.tsx [เดา]"), not at the end of the line. Print the four lines as plain text: no code fence, no heading, no prefix. If the ask cannot be made concrete without one fact only
the user has, ask that one question inline in the brief, not as a separate turn.

Ask yourself before showing it: can this be done by one agent in this session? If it is one feature,
yes. Do not plan subagents; they cost 2× corrections in this user's history.

## 2. One stop

Show the brief and stop with exactly this line, flush left, no code fence: `ตอบ "ทำ" หรือแก้บรรทัดที่ผิด`
If `$ARGUMENTS` starts with `!` (the user typed `/go !งาน`), the brief is pre-confirmed: print it and continue immediately. (`/go!` is not a command the CLI knows; it is `/go !`.)

## 3. Run to the end

After "ทำ" (or edits): do the whole thing. Do not stop to ask, do not report progress, do not use
AskUserQuestion. When a choice comes up, take the one that touches fewer files and note it for the recap.
No comments in code. No dev server left running that you started.

## 4. Verify, then recap

Run the `เสร็จเมื่อ` check yourself (browser via chrome-devtools MCP, storybook, or the command) and
look at the result, not just the exit code. Recap in one short paragraph: what changed, what you chose
on your own, what the check showed, and anything from `ห้าม` you had to bend. Then stop.
The user will `/ship` when they are satisfied.
