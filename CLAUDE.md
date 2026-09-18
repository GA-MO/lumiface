# Lumiface

Monorepo: `server/` (FastAPI, judges everything), `packages/lumiface` (Flutter SDK), `packages/lumiface-react`,
`examples/` (flutter, react, backend), `website/` (docs + landing, fumadocs), `docs/plans/face-check-in.md` (status).

## Docs move with the code
The docs under `website/content/docs`, `README.md` and `server/README.md` describe behaviour, not aspirations.
A change to any of these must update the docs in the same commit:
- a reason code, stream event, policy field, env var, endpoint or protocol message (`server/app`)
- an SDK public API, state, phase, hint or config field (`packages/*`)
- a claim about what the device vs the server decides (`concepts.mdx`, `security.mdx`, `api.mdx`)
`bun run check:docs` (in the ship gate) fails when a code name or event is missing from the docs; it cannot
read prose, so grep the docs for the old wording before shipping (`grep -rn "<old term>" website/content/docs README.md server/README.md`).
When a phase closes (or any change to the protocol, the pipeline order, what the device vs the server decides,
or an SDK's public surface), read these in full against the code, claim by claim, not by grep:
`concepts.mdx`, `api.mdx`, `security.mdx`, `get-started.mdx`, `server/index.mdx`, `flutter/index.mdx`,
`react/index.mdx`, `roadmap.mdx`, `README.md`, `server/README.md`. Grep finds renamed words; only reading finds
"uploads seven frames" after the stream replaced uploads. Verify every prop, field, env var and table name
listed in a doc against the source that defines it. Record what was measured with a date and the device.
The landing-page demo (`website/app/components/home/live-demo-runner.tsx`) runs the real SDK against a stand-in
server that judges nothing; keep its copy saying so.

## Gates
`.claude/ship.md` has the ship gate. Phone tests: Galaxy S25+ over USB with `adb reverse tcp:8000 tcp:8000`
and `tcp:8010`; release builds only (debug hides R8 problems).

## Live tests are a dataset, not a ritual
Run the server with `STORE_FRAMES=1 DEBUG=1` whenever the user is about to test in front of a camera; every
session lands in `server/data/frames/<project>/<session>/` with a replayable `session.json`. After the round,
copy the sessions into `server/data/sessions/genuine/` or `attack/` (the user says which was which) and keep
`server/data/sessions/subjects/<id>.npy` for the enrolled face. `uv run python scripts/replay_sessions.py <folder>`
re-runs the pipeline on any session; `tests/test_replay.py` (in the pytest gate) requires every genuine session to
pass and every attack to be refused. A server-side change (windows, thresholds, placement) is verified against the
set first; the user is asked for a new live round only for what the set cannot show (a new device, a client change).
