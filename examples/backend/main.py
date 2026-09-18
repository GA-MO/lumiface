"""The example apps' backend: the part of *your* system that holds the project key.

Lumiface itself never talks to an anonymous device about who it is. Your application backend
does: it knows who is logged in, asks Lumiface for a session bound to that subject with the
project key, hands the session to the app, and afterwards reads the outcome for itself. This
app is a stand-in for that backend so the Flutter example and the React demo can run the real
flow on a laptop. It is not part of Lumiface; it only needs FastAPI and httpx. Run it next to
the Lumiface server:

    cd examples/backend
    LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me uv run uvicorn main:app --port 8010

There is no login here — the app names the subject — which is the one thing a real backend
must not let the device do.
"""
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


class SessionIn(BaseModel):
    subject_id: str | None = None
    purpose: str = "demo"


class EnrolTokenIn(BaseModel):
    subject_id: str
    name: str = ""


class DoneIn(BaseModel):
    session_id: str


@app.post("/api/face/session")
async def create_session(body: SessionIn, request: Request):
    """The subject is fixed here. A real backend takes it from its own login, never from the device."""
    return await forward(await lumiface(request).post("/v1/sessions", json={"subject_id": body.subject_id, "purpose": body.purpose}))


@app.post("/api/face/enrol-token")
async def create_enrol_token(body: EnrolTokenIn, request: Request):
    return await forward(await lumiface(request).post("/v1/subjects/tokens", json={"external_id": body.subject_id, "name": body.name}))


@app.post("/api/face/done")
async def done(body: DoneIn, request: Request):
    """The verdict the app acts on comes from here, never from what the device reports."""
    return await forward(await lumiface(request).get(f"/v1/sessions/{body.session_id}"))


# Admin-style helpers the example apps' other tabs use (subjects, history, policy).
@app.get("/api/face/subjects")
async def list_subjects(request: Request):
    return await forward(await lumiface(request).get("/v1/subjects"))


@app.post("/api/face/subjects")
async def enrol_photo(request: Request, external_id: str = Form(...), name: str = Form(""),
                      replace: bool = Form(False), photo: UploadFile = File(...)):
    r = await lumiface(request).post("/v1/subjects", data={"external_id": external_id, "name": name, "replace": str(replace).lower()},
                                     files={"photo": (photo.filename or "photo.jpg", await photo.read(), photo.content_type or "image/jpeg")})
    return await forward(r)


@app.delete("/api/face/subjects/{external_id}", status_code=204)
async def delete_subject(external_id: str, request: Request):
    await forward(await lumiface(request).delete(f"/v1/subjects/{external_id}"))


@app.get("/api/face/verifications")
async def list_verifications(request: Request, purpose: str | None = None, subject_id: str | None = None, limit: int = 100):
    params = {k: v for k, v in {"purpose": purpose, "subject_id": subject_id, "limit": limit}.items() if v is not None}
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
