# Demo backend

The one process on the internet that holds the demo project's key. The live demo on the docs home runs the
real React SDK; the page is static (GitHub Pages) so it cannot hold a key, and this ~100-line FastAPI app
mints its sessions the way any customer backend does ([`examples/backend`](../../examples/backend)), with what
a public endpoint needs on top: liveness only (no photo, no user), `DEMO_RATE` sessions an hour per IP, and
nothing else of the project exposed (no policy, no audit log, no other session's verdict). It is not part of
the Lumiface server and needs none of its models.

| Route | Does |
|---|---|
| `POST /demo/session` | `POST /v1/sessions` with the key and no photo, answers `{server, session}`: where the browser streams to and Lumiface's session JSON as is (the SDK's `sessionFromJson` reads it). 429 `DEMO_RATE_LIMITED` past `DEMO_RATE` |
| `POST /demo/done` `{session_id}` | `GET /v1/sessions/{id}` with the key for a session minted here, answers `{used, ok, reason_code}` and nothing more; 404 `SESSION_NOT_FOUND` for any other |
| `GET /health` | `{ok, lumiface_up}` |

| Variable | Default | |
|---|---|---|
| `LUMIFACE_URL` | `http://localhost:8000` | the server, as this process reaches it |
| `LUMIFACE_PUBLIC_URL` | `LUMIFACE_URL` | the server as the browser reaches it (TLS in front, `wss://` for the stream) |
| `LUMIFACE_KEY` | `lf_sk_change-me` | the demo project's key; one project just for the demo, so its policy and audit log are its own |
| `DEMO_ORIGINS` | `*` | comma-separated CORS origins; set it to the docs site's origin |
| `DEMO_RATE` | `20` | sessions per IP per hour, `0` for unlimited |
| `DEMO_TRUST_PROXY` | `0` | `1` behind a reverse proxy: the client IP comes from `X-Forwarded-For` |

```bash
cd website/demo-backend
LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_... uv run uvicorn main:app --port 8020
# or from the repo root: bun run dev:demo-backend
```

## Deploying the demo

It runs on Fly.io (region `sin`) as two apps from the two `fly.toml`s, both public over TLS (the browser opens
the stream on the server directly, `wss://`):

| App | Config | Machine | URL |
|---|---|---|---|
| `lumiface-demo` (server) | `server/fly.toml` | shared-cpu-2x, 2 GB, volume `lumiface_data` 3 GB (SQLite + the InsightFace models via `INSIGHTFACE_HOME`) | https://lumiface-demo.fly.dev |
| `lumiface-demo-api` (this app) | `website/demo-backend/fly.toml` | shared-cpu-1x, 256 MB | https://lumiface-demo-api.fly.dev |

```bash
# once: apps, volume, one key for both sides
flyctl apps create lumiface-demo && flyctl apps create lumiface-demo-api
flyctl volumes create lumiface_data --app lumiface-demo --region sin --size 3
KEY="lf_sk_$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
flyctl secrets set BOOTSTRAP_API_KEY="$KEY" --app lumiface-demo --stage
flyctl secrets set LUMIFACE_KEY="$KEY" --app lumiface-demo-api --stage
# every release
(cd server && flyctl deploy --remote-only --ha=false)
(cd website/demo-backend && flyctl deploy --remote-only --ha=false)
```

The docs site is built with `VITE_LUMIFACE_DEMO_URL` set to this app's URL: the `LUMIFACE_DEMO_URL` repository
variable feeds the Pages workflow (`gh variable set LUMIFACE_DEMO_URL --body https://lumiface-demo-api.fly.dev`).
Unset, the site's demo runs a stand-in in the browser that judges nothing and says so.

What the demo's copy promises, and the box must keep (both are in `server/fly.toml`):

- `STORE_FRAMES=0` and `DEBUG=0` on the server: no frame outlives the verdict. The audit row keeps `ok`, the
  reason code and the scores, never a frame or a face.
- Sessions are single use, expire with their TTL and are purged after `SESSION_PURGE_GRACE_SECONDS`.
- `MAX_OPEN_STREAMS=8` (the server closes the socket `SERVER_BUSY` past it, and the demo shows that as a failed
  attempt to retry), `DEMO_RATE` on, `DEMO_ORIGINS` set to the docs site's origin.
- Both machines are billed only while awake (well under a dollar a month at demo traffic). The server is
  *suspended* when idle (`auto_stop_machines = "suspend"`: a RAM snapshot, so the models stay loaded and the next
  request resumes it in under a second); suspend needs the machine at 2 GB or less, hence `MAX_CONCURRENT_ANALYSES=1`
  (a second session queues in the pool). The demo backend simply stops and starts in a second or two.

Measured 2026-09-21 from a laptop in Bangkok: with the server *stopped* (the previous setting, and what happens after
a deploy) the session arrived after 25 s and the plan 17 s later while the models loaded, and visitors left; with the
server *suspended* the first request resumes it in 0.8 s, then the session arrives in 0.2 s, the plan 0.2 s later, and
the verdict about 11 s after `end` (3 s on an M-series laptop). The server sits at ~950 MB with the models loaded and
peaks at ~1.2 GB while judging.

Locally: run the server (`cd server && uv run uvicorn app.main:app --port 8000`), this app, then
`VITE_LUMIFACE_DEMO_URL=http://localhost:8020 bun run dev:site` and open http://localhost:3002.
