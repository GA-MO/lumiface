"""The docs site's demo backend: the one process on the internet that holds the demo project's key.

The live demo on the docs home runs the real React SDK against a real Lumiface server. The page is
static (GitHub Pages) so it cannot hold a key; this app mints the sessions for it, the way any
customer backend does (`examples/backend`), with two differences a public endpoint needs: every
session is liveness only (nobody's photo is involved) and each IP gets `DEMO_RATE` sessions an hour.
It exposes nothing else of the project: no policy, no audit log, no other session's verdict. Run it
next to the Lumiface server:

    cd website/demo-backend
    LUMIFACE_URL=http://localhost:8000 LUMIFACE_PUBLIC_URL=https://demo.example.com \
    LUMIFACE_KEY=lf_sk_... DEMO_ORIGINS=https://you.github.io uv run uvicorn main:app --port 8020

The Lumiface server behind it must run with `STORE_FRAMES=0` and `DEBUG=0` (the defaults): the demo
copy promises the visitor that no frame outlives the verdict.
"""
import os
import time
from collections import deque

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

LUMIFACE_URL = os.environ.get("LUMIFACE_URL", "http://localhost:8000")
# Where the browser opens the stream; the same host as LUMIFACE_URL seen from outside (TLS, wss://).
LUMIFACE_PUBLIC_URL = os.environ.get("LUMIFACE_PUBLIC_URL", LUMIFACE_URL)
LUMIFACE_KEY = os.environ.get("LUMIFACE_KEY", "lf_sk_change-me")
DEMO_ORIGINS = [o.strip() for o in os.environ.get("DEMO_ORIGINS", "*").split(",") if o.strip()]
DEMO_RATE = int(os.environ.get("DEMO_RATE", "20"))  # sessions per IP per hour; 0 = unlimited
DEMO_TRUST_PROXY = os.environ.get("DEMO_TRUST_PROXY", "0") == "1"  # read the client IP from X-Forwarded-For
PURPOSE = "website-demo"
WINDOW_SECONDS = 3600

app = FastAPI(title="Lumiface demo backend", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=DEMO_ORIGINS, allow_methods=["POST", "GET"], allow_headers=["*"])


def lumiface(request: Request) -> httpx.AsyncClient:
    """One client per app; tests swap in an in-process transport through `app.state`."""
    client = getattr(request.app.state, "lumiface", None)
    if client is None:
        client = httpx.AsyncClient(base_url=LUMIFACE_URL, headers={"X-API-Key": LUMIFACE_KEY}, timeout=60)
        request.app.state.lumiface = client
    return client


async def forward(r: httpx.Response):
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text)
    return r.json() if r.content else None


# Sessions this process minted, so `/demo/done` answers for those only and `DEMO_RATE` counts per IP.
SESSIONS: set[str] = set()
RECENT: dict[str, deque[float]] = {}


def client_ip(request: Request) -> str:
    if DEMO_TRUST_PROXY and (fwd := request.headers.get("x-forwarded-for")):
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def take_slot(ip: str, now: float | None = None) -> bool:
    """One session from `DEMO_RATE` per hour for this IP; False when they are spent."""
    if DEMO_RATE <= 0:
        return True
    now = time.monotonic() if now is None else now
    q = RECENT.setdefault(ip, deque())
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    if len(q) >= DEMO_RATE:
        return False
    q.append(now)
    return True


class DoneIn(BaseModel):
    session_id: str


@app.post("/demo/session")
async def create_session(request: Request):
    """A liveness session for the visitor's browser: Lumiface's JSON as is (the SDK's `sessionFromJson` reads it)
    plus where the stream goes. No photo, no user: the demo proves a person is there, never who."""
    if not take_slot(client_ip(request)):
        raise HTTPException(429, {"reason_code": "DEMO_RATE_LIMITED", "detail": f"{DEMO_RATE} demo sessions an hour per address"})
    session = await forward(await lumiface(request).post("/v1/sessions", json={"reference_photo": None, "purpose": PURPOSE}))
    SESSIONS.add(session["session_id"])
    return {"server": LUMIFACE_PUBLIC_URL, "session": session}


@app.post("/demo/done")
async def done(body: DoneIn, request: Request):
    """What a backend acts on: the verdict read with the key, never the device's copy. Only for sessions minted
    here, and only the verdict: the scores and `details` stay with the project."""
    if body.session_id not in SESSIONS:
        raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
    status = await forward(await lumiface(request).get(f"/v1/sessions/{body.session_id}"))
    result = status["result"]
    return {"used": status["used"], "ok": bool(result and result["ok"]), "reason_code": result["reason_code"] if result else None}


@app.get("/health")
async def health(request: Request):
    try:
        up = (await lumiface(request).get("/health")).status_code == 200
    except httpx.HTTPError:
        up = False
    return {"ok": True, "lumiface_up": up}
