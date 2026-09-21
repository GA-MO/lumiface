"""The example apps' backend: the part of *your* system that holds the project key.

Lumiface itself never talks to an anonymous device about who it is, and it keeps no faces. Your
application backend does both: it has the users and their photos, it knows who is logged in, it
asks Lumiface for a session with that user's photo as the reference (project key), hands the
session to the app, and afterwards reads the outcome for itself. This app is a stand-in for that
backend so the Flutter example and the React demo can run the real flow on a laptop: its "users"
are an in-memory dict of `{name, photo}` filled from the apps' Users tab. It is not part of
Lumiface; it only needs FastAPI and httpx. Run it next to the Lumiface server:

    cd examples/backend
    LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me uv run uvicorn main:app --port 8010

There is no login here — the app names the user — which is the one thing a real backend
must not let the device do.
"""
import base64
import os

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

LUMIFACE_URL = os.environ.get("LUMIFACE_URL", "http://localhost:8000")
LUMIFACE_KEY = os.environ.get("LUMIFACE_KEY", "lf_sk_change-me")

app = FastAPI(title="Lumiface example backend", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


# Your user store. Here a dict that lives as long as the process; in a real backend, your users table.
USERS: dict[str, dict] = {}
# Which user each session was created for. Lumiface's verdict names no user (it keeps none), so this
# is what `/api/face/done` decides with — never what the device says.
SESSIONS: dict[str, str | None] = {}


class SessionIn(BaseModel):
    user_id: str | None = None  # whose photo to verify against; omitted = liveness only
    purpose: str = "demo"


class DoneIn(BaseModel):
    session_id: str


@app.post("/api/face/session")
async def create_session(body: SessionIn, request: Request):
    """Who gets verified is fixed here, from the user's own photo in this backend's records. A real backend
    takes the user from its login, never from the device; Lumiface only ever sees the photo, for one session."""
    photo = None
    if body.user_id:
        user = USERS.get(body.user_id)
        if not user:
            raise HTTPException(404, {"reason_code": "USER_NOT_FOUND"})
        photo = base64.b64encode(user["photo"]).decode()
    session = await forward(await lumiface(request).post("/v1/sessions", json={"reference_photo": photo, "purpose": body.purpose}))
    SESSIONS[session["session_id"]] = body.user_id or None
    return session  # straight to the device: it holds only the session token


@app.post("/api/face/done")
async def done(body: DoneIn, request: Request):
    """The verdict the app acts on comes from here, never from what the device reports: Lumiface's status,
    joined with this backend's own record of who the session was for."""
    status = await forward(await lumiface(request).get(f"/v1/sessions/{body.session_id}"))
    user_id = SESSIONS.get(body.session_id)
    verified = bool(status["result"] and status["result"]["ok"] and status["reference"] and user_id)
    # A real backend now grants what the session was for (signs in `user_id`, unlocks the feature).
    return {**status, "user_id": user_id, "verified": verified}


# The user store the example apps' Users tab fills: a registration photo per user, kept here and nowhere else.
@app.get("/api/users")
async def list_users():
    return [{"id": uid, "name": u["name"]} for uid, u in USERS.items()]


@app.post("/api/users", status_code=201)
async def register_user(user_id: str = Form(...), name: str = Form(""), photo: UploadFile = File(...)):
    USERS[user_id] = {"name": name, "photo": await photo.read()}
    return {"id": user_id, "name": name}


@app.delete("/api/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    USERS.pop(user_id, None)


# Admin-style helpers the example apps' other tabs use (history, policy).
@app.get("/api/face/verifications")
async def list_verifications(request: Request, purpose: str | None = None, limit: int = 100):
    params = {k: v for k, v in {"purpose": purpose, "limit": limit}.items() if v is not None}
    return await forward(await lumiface(request).get("/v1/verifications", params=params))


@app.get("/api/face/policy")
async def get_policy(request: Request):
    return await forward(await lumiface(request).get("/v1/policy"))


class PolicyIn(BaseModel):
    preset: str | None = None
    overrides: dict | None = None
    merge: bool = True


@app.put("/api/face/policy")
async def update_policy(body: PolicyIn, request: Request):
    return await forward(await lumiface(request).put("/v1/policy", json=body.model_dump(exclude_none=True)))


@app.get("/api/face/policy/presets")
async def list_presets(request: Request):
    return await forward(await lumiface(request).get("/v1/policy/presets"))


@app.get("/health")
async def health(request: Request):
    try:
        up = (await lumiface(request).get("/health")).status_code == 200
    except httpx.HTTPError:
        up = False
    return {"ok": True, "lumiface": LUMIFACE_URL, "lumiface_up": up}
