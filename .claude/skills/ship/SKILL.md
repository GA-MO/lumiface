---
name: ship
description: Finish the mechanical tail of a task in one step — commit only this session's files, optionally deploy (e.g. /ship uat), stop dev servers this session started, and report one line. User-invoked only.
disable-model-invocation: true
argument-hint: "[uat|sit|none]"
allowed-tools: Bash(git *), Bash(lsof *), Bash(kill *), Bash(make *), Bash(bun *), Bash(npm *), Bash(curl *), Read
---

# /ship — commit · deploy · close

The user has decided the work is done. Do not re-open design questions, do not ask
anything, do not touch files. Everything below is mechanical; finish it and report one line.

Target: `$ARGUMENTS` — empty = commit only · `uat` / `sit` = commit then deploy there · `none` = close servers only.

## 0. Recipe

Read `.claude/ship.md` in the project root if it exists. It has lines:

    gate: <command that must pass before commit>
    deploy uat: <command>
    deploy sit: <command>
    smoke: <url or command to check after deploy>
    ports: <dev-server ports this project uses>

No recipe → gate = none; deploy = `git push` current branch; ports = 3000 5173 6006.

## 1. Stage only what this session changed

- `git status --porcelain`. Stage **only** files this conversation edited or created.
  Never `git add -A`, `-u`, or `.` — other sessions may be working in the same tree.
- Files changed on disk that this session did not touch: leave them unstaged, mention them in the report.
- Nothing to stage → skip to step 4.
- **This session edited nothing** (fresh session, or resumed after compaction) but `git status` shows changes: do not end with 0 files. List the changed files in one line — `ไม่รู้ว่าไฟล์ไหนเป็นของ session นี้: <files> — ตอบชื่อไฟล์ที่จะ commit` — and stop. This is the one exception to "do not ask".
- Before committing, read `git diff --cached`. If a staged file also contains hunks this session did not write (another session touched the same file), commit anyway but add `swept in: <file>:<lines>` to the report.

## 2. Gate

Run the recipe `gate`. If it fails because of this session's change, fix that and re-run once.
If it fails for any other reason, stop: unstage nothing, report the failure verbatim, do not commit.

## 3. Commit

One commit. Subject in the project's existing style (`git log -5 --format=%s`), under 70 chars,
body only if the diff needs a why. No file lists, no trailers you add yourself.

## 4. Deploy (only when asked)

Run the recipe `deploy <target>` exactly. Print the pipeline / remote URL it results in.
Then `smoke`: a URL → `curl -sS -o /dev/null -w '%{http_code}'` (report the code, don't wait for a
pipeline to finish); a command → run it and report pass/fail.
Return to the branch you started on.

## 5. Close what this session opened

For each recipe `ports` entry: `lsof -tiTCP:<port> -sTCP:LISTEN`. Kill only processes this session
started (you know their commands). A server that was already running when the session began stays.
Confirm with a second `lsof`.

## 6. Report — one line

    shipped <short-sha> "<subject>" · <n> files · deploy: <target|none> <http-code> · closed: <ports|none> · left unstaged: <files|none>

Nothing was staged → `nothing to ship · left unstaged: <files|none> · closed: <ports|none>`
Flush left, no code fence. Then stop. No summary, no next steps.
