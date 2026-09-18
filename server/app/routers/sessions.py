import asyncio
import json
import time
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, col, select

from ..config import get_settings
from ..db import get_db, get_engine
from ..deps import bearer_token, current_project, new_token, project_for_token, token_matches
from ..models import Project, Verification, VerifySession, utcnow
from ..policy import ClientPolicy, get_policy
from ..services.challenge import new_challenges
from ..services.flash import new_flash_colors
from ..services.stream import StreamEvent, StreamFrame, VerifyResult, analyze_stream
from .subjects import find_subject

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

PURPOSE_MAX = 40
EVENT_NAMES = ("aligned", "challenge_done", "flash", "flash_end")


class SessionCreate(BaseModel):
    subject_id: str | None = None
    purpose: str = Field("", max_length=PURPOSE_MAX)


class SessionOut(BaseModel):
    """What the backend hands the device. The plan (challenges, colours) only travels over the stream."""

    session_id: str
    session_token: str
    mode: str
    purpose: str
    expires_at: str
    ttl_seconds: int
    client_config: ClientPolicy


class Scores(BaseModel):
    match: float | None = None
    spoof: float | None = None
    consistency: float | None = None


class VerifyOut(BaseModel):
    ok: bool
    mode: str
    reason_code: str
    scores: Scores
    verification_id: int | None = None
    details: dict = {}


class SessionStatus(BaseModel):
    """What the backend reads with the project key once the device says it is done."""

    session_id: str
    mode: str
    subject_id: str | None
    purpose: str
    used: bool
    expires_at: str
    result: VerifyOut | None


def _mode(subject_id: str | None) -> str:
    return "verify" if subject_id else "liveness"


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate | None = None, project: Project = Depends(current_project),
                   db: Session = Depends(get_db)):
    p = get_policy()
    body = body or SessionCreate()
    sess = VerifySession(
        id=uuid.uuid4().hex,
        project_id=project.id,
        token=new_token(),
        subject_external_id=body.subject_id,
        purpose=body.purpose,
        challenges=",".join(new_challenges()),
        flash_colors=",".join(new_flash_colors()),
        expires_at=utcnow() + timedelta(seconds=p.session_ttl_seconds),
    )
    db.add(sess)
    db.commit()
    return SessionOut(session_id=sess.id, session_token=sess.token, mode=_mode(body.subject_id), purpose=body.purpose,
                      expires_at=sess.expires_at.isoformat() + "Z", ttl_seconds=p.session_ttl_seconds,
                      client_config=p.client)


def _verify_out(row: Verification, details: dict | None = None) -> VerifyOut:
    return VerifyOut(ok=row.ok, mode=_mode(row.subject_external_id), reason_code=row.reason_code,
                     scores=Scores(match=row.match_score, spoof=row.spoof_score, consistency=row.consistency_score),
                     verification_id=row.id if row.ok else None, details=details or {})


@router.get("/{session_id}", response_model=SessionStatus)
def get_session(session_id: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    """Backend-side outcome of a session; the device's own report of success is never to be trusted."""
    sess = db.get(VerifySession, session_id)
    if not sess or sess.project_id != project.id:
        raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
    row = db.exec(select(Verification).where(Verification.session_id == session_id)).first()
    return SessionStatus(session_id=sess.id, mode=_mode(sess.subject_external_id), subject_id=sess.subject_external_id,
                         purpose=sess.purpose, used=sess.used, expires_at=sess.expires_at.isoformat() + "Z",
                         result=_verify_out(row) if row else None)


def _store_frames(project_id: int, session_id: str, frames: list[StreamFrame], events: list[StreamEvent],
                  challenges: list[str], flash_colors: list[str], subject_id: str | None,
                  client_info: dict, result: VerifyResult) -> None:
    """The whole streamed session as the server saw it, replayable by `scripts/replay_sessions.py`
    against a changed pipeline without anyone in front of a camera again: every frame with both
    clocks, the events, the plan, and the verdict this run produced."""
    d = Path(get_settings().frames_dir).resolve() / str(project_id) / session_id
    d.mkdir(parents=True, exist_ok=True)
    t0 = frames[0].recv_ms if frames else 0
    names = []
    for i, f in enumerate(frames):
        names.append(f"{i:04d}_{f.recv_ms - t0:06d}.jpg")
        (d / names[-1]).write_bytes(f.data)
    (d / "session.json").write_text(json.dumps({
        "session_id": session_id, "subject_id": subject_id, "challenges": challenges, "flash_colors": flash_colors,
        "client": client_info, "verdict": {"ok": result.ok, "reason_code": result.reason_code},
        "frames": [{"file": n, "recv_ms": f.recv_ms, "client_ms": f.client_ms} for n, f in zip(names, frames)],
        "events": [{"name": e.name, "index": e.index, "recv_ms": e.recv_ms, "client_ms": e.client_ms} for e in events],
    }, indent=1))


class _StreamError(Exception):
    def __init__(self, reason_code: str, close_code: int = 1008) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.close_code = close_code


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


@router.websocket("/{session_id}/stream")
async def stream_session(ws: WebSocket, session_id: str):
    """The device's side of a verification.

    1. `{"type": "hello", "token": <session_token>, "client": {...}}`
    2. <- `{"type": "plan", "challenges": [...], "flash_colors": [...], "flash_hold_ms": n, "client_config": {...}}`
    3. binary frames: 8-byte big-endian client time in ms, then a JPEG; sent continuously
       text events: `{"type": "event", "name": "aligned" | "challenge_done" | "flash" | "flash_end", "index"?: i, "ts": ms}`
    4. `{"type": "end"}` -> <- `{"type": "result", ...}` and the socket closes.
    The server clocks everything itself; the session is spent as soon as the hello is accepted.
    """
    s = get_settings()
    await ws.accept()
    frames: list[StreamFrame] = []
    events: list[StreamEvent] = []
    total_bytes = 0
    try:
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
        except (asyncio.TimeoutError, ValueError):
            raise _StreamError("HELLO_INVALID")
        if not isinstance(hello, dict) or hello.get("type") != "hello":
            raise _StreamError("HELLO_INVALID")
        try:
            token = bearer_token(f"Bearer {hello.get('token', '')}") if hello.get("token") else None
        except HTTPException:
            token = None
        client_info = hello.get("client") if isinstance(hello.get("client"), dict) else {}
        # The browser's own description of itself, so the audit log tells iOS Safari from desktop Chrome.
        if ws.headers.get("user-agent"):
            client_info = {**client_info, "user_agent": ws.headers["user-agent"][:200]}

        with Session(get_engine()) as db:
            sess = db.get(VerifySession, session_id)
            if not sess or not token_matches(token, sess.token):
                raise _StreamError("SESSION_NOT_FOUND")
            project = project_for_token(db, sess.project_id)
            if sess.expires_at < utcnow():
                raise _StreamError("SESSION_EXPIRED")
            claimed = db.exec(update(VerifySession).where(col(VerifySession.id) == session_id,
                                                          col(VerifySession.used) == False).values(used=True))  # noqa: E712
            db.commit()
            if claimed.rowcount != 1:
                raise _StreamError("SESSION_USED")
            subject = find_subject(db, project, sess.subject_external_id) if sess.subject_external_id else None
            if sess.subject_external_id and not subject:
                raise _StreamError("SUBJECT_NOT_FOUND")
            enrolled = np.frombuffer(subject.embedding, dtype=np.float32) if subject else None
            challenges = sess.challenges.split(",")
            flash_colors = [c for c in sess.flash_colors.split(",") if c]
            deadline = _now_ms() + int((sess.expires_at - utcnow()).total_seconds() * 1000)
            project_id, purpose, subject_id = project.id, sess.purpose, sess.subject_external_id
            subject_row_id = subject.id if subject else None
        p = get_policy()

        await ws.send_json({"type": "plan", "challenges": challenges, "flash_colors": flash_colors,
                            "flash_hold_ms": p.flash_hold_ms, "client_config": p.client.model_dump()})

        while True:
            remaining = deadline - _now_ms()
            if remaining <= 0:
                raise _StreamError("SESSION_EXPIRED")
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=remaining / 1000)
            except asyncio.TimeoutError:
                raise _StreamError("SESSION_EXPIRED")
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            now = _now_ms()
            if msg.get("bytes") is not None:
                data = msg["bytes"]
                if len(data) < 8 or len(data) - 8 > s.max_frame_bytes:
                    raise _StreamError("PAYLOAD_TOO_LARGE", 1009)
                total_bytes += len(data)
                if total_bytes > s.max_upload_bytes or len(frames) >= s.max_stream_frames:
                    raise _StreamError("PAYLOAD_TOO_LARGE", 1009)
                frames.append(StreamFrame(recv_ms=now, client_ms=int.from_bytes(data[:8], "big"), data=data[8:]))
                continue
            try:
                ev = json.loads(msg.get("text") or "")
            except ValueError:
                raise _StreamError("EVENT_INVALID")
            if not isinstance(ev, dict):
                raise _StreamError("EVENT_INVALID")
            if ev.get("type") == "end":
                events.append(StreamEvent(name="end", recv_ms=now))
                break
            if ev.get("type") != "event" or ev.get("name") not in EVENT_NAMES:
                raise _StreamError("EVENT_INVALID")
            index = ev.get("index")
            events.append(StreamEvent(name=ev["name"], recv_ms=now, index=index if isinstance(index, int) else None,
                                      client_ms=ev.get("ts") if isinstance(ev.get("ts"), int) else None))

        result = await asyncio.to_thread(analyze_stream, frames, events, challenges, flash_colors, enrolled)
        if s.store_frames and (s.debug or not result.ok):
            await asyncio.to_thread(_store_frames, project_id, session_id, frames, events, challenges, flash_colors,
                                    subject_id, client_info, result)
        t0 = frames[0].recv_ms if frames else 0
        with Session(get_engine()) as db:
            row = Verification(project_id=project_id, subject_id=subject_row_id, subject_external_id=subject_id,
                               purpose=purpose, session_id=session_id, ok=result.ok, reason_code=result.reason_code,
                               match_score=result.match_score, spoof_score=result.spoof_score,
                               consistency_score=result.consistency_score,
                               details=json.dumps({**result.details, "challenges": challenges,
                                                   "flash_colors": flash_colors, "client": client_info,
                                                   "events": [{"name": e.name, "index": e.index, "t": e.recv_ms - t0}
                                                              for e in events]}))
            db.add(row)
            db.commit()
            db.refresh(row)
        # Per-frame scores are a tuning oracle: the device gets the verdict, the backend the details.
        await ws.send_json({"type": "result", **_verify_out(row).model_dump()})
        await ws.close(code=1000)
    except WebSocketDisconnect:
        return
    except _StreamError as e:
        try:
            await ws.send_json({"type": "error", "reason_code": e.reason_code})
            await ws.close(code=e.close_code)
        except RuntimeError:
            pass
