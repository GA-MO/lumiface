import asyncio
import base64
import binascii
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
from ..services.challenge import new_challenges, oval_for
from ..services.video import FORMATS, VideoChunk, decode_chunks
from ..services.flash import new_flash_colors
from ..services.stream import StreamEvent, StreamFrame, VerifyResult, analyze_stream
from ..services.verify import reference as check_reference

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

PURPOSE_MAX = 40
EVENT_NAMES = ("aligned", "challenge_done", "flash", "flash_end")


class SessionCreate(BaseModel):
    # Base64 JPEG/PNG of the person to match (a `data:` URL prefix is tolerated); omitted = liveness only.
    # Only its embedding reaches the session row, and only until the stream claims it.
    reference_photo: str | None = None
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
    reference: bool  # a reference photo was given at creation (verify) or not (liveness)
    purpose: str
    used: bool
    expires_at: str
    result: VerifyOut | None


def _mode(reference: bool) -> str:
    return "verify" if reference else "liveness"


def _reference_embedding(photo_b64: str) -> bytes:
    """The photo becomes an embedding here and is dropped; one frontal face, no anti-spoof (see services.verify)."""
    if "," in photo_b64[:64] and photo_b64.startswith("data:"):
        photo_b64 = photo_b64.split(",", 1)[1]
    try:
        data = base64.b64decode(photo_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, {"reason_code": "BAD_IMAGE", "detail": "reference_photo is not base64"})
    if len(data) > get_settings().max_frame_bytes:
        raise HTTPException(413, {"reason_code": "PAYLOAD_TOO_LARGE"})
    result = check_reference(data)
    if not result.ok:
        raise HTTPException(422, {"reason_code": result.reason_code, "details": result.details})
    assert result.embedding is not None
    return result.embedding.astype(np.float32).tobytes()


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate | None = None, project: Project = Depends(current_project),
                   db: Session = Depends(get_db)):
    p = get_policy()
    body = body or SessionCreate()
    embedding = _reference_embedding(body.reference_photo) if body.reference_photo else None
    sess = VerifySession(
        id=uuid.uuid4().hex,
        project_id=project.id,
        token=new_token(),
        reference=embedding is not None,
        reference_embedding=embedding,
        purpose=body.purpose,
        challenges=",".join(new_challenges()),
        flash_colors=",".join(new_flash_colors()),
        expires_at=utcnow() + timedelta(seconds=p.session_ttl_seconds),
    )
    db.add(sess)
    db.commit()
    return SessionOut(session_id=sess.id, session_token=sess.token, mode=_mode(sess.reference), purpose=body.purpose, expires_at=sess.expires_at.isoformat() + "Z", ttl_seconds=p.session_ttl_seconds,
                      client_config=p.client)


def _verify_out(row: Verification, details: dict | None = None) -> VerifyOut:
    return VerifyOut(ok=row.ok, mode=_mode(row.reference), reason_code=row.reason_code,
                     scores=Scores(match=row.match_score, spoof=row.spoof_score, consistency=row.consistency_score),
                     verification_id=row.id if row.ok else None, details=details or {})


@router.get("/{session_id}", response_model=SessionStatus)
def get_session(session_id: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    """Backend-side outcome of a session; the device's own report of success is never to be trusted."""
    sess = db.get(VerifySession, session_id)
    if not sess or sess.project_id != project.id:
        raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
    row = db.exec(select(Verification).where(Verification.session_id == session_id)).first()
    return SessionStatus(session_id=sess.id, mode=_mode(sess.reference), reference=sess.reference, purpose=sess.purpose,
                         used=sess.used, expires_at=sess.expires_at.isoformat() + "Z",
                         result=_verify_out(row) if row else None)


def _store_frames(project_id: int, session_id: str, frames: list[StreamFrame], events: list[StreamEvent],
                  challenges: list[str], flash_colors: list[str], reference: np.ndarray | None, client_info: dict,
                  result: VerifyResult, fmt: str = "jpeg", chunks: list[VideoChunk] | None = None) -> None:
    """The whole streamed session as the server saw it, replayable by `scripts/replay_sessions.py`
    against a changed pipeline without anyone in front of a camera again: every frame with both
    clocks, the events, the plan, and the verdict this run produced. A video stream is kept as the
    device sent it too (`stream.<format>`, the raw chunks in order), the decoded frames are what replay.
    The reference embedding goes in as `reference.npy` so the match can be replayed: this store is the
    development setting that already keeps every frame of the person, never the production one."""
    d = Path(get_settings().frames_dir).resolve() / str(project_id) / session_id
    d.mkdir(parents=True, exist_ok=True)
    if chunks:
        (d / f"stream.{fmt}").write_bytes(b"".join(c.data for c in chunks))
    if reference is not None:
        np.save(d / "reference.npy", reference)
    t0 = frames[0].recv_ms if frames else 0
    names = []
    for i, f in enumerate(frames):
        names.append(f"{i:04d}_{f.recv_ms - t0:06d}.jpg")
        (d / names[-1]).write_bytes(f.data)
    (d / "session.json").write_text(json.dumps({
        "session_id": session_id, "reference": reference is not None, "challenges": challenges, "flash_colors": flash_colors,
        "client": client_info, "format": fmt, "verdict": {"ok": result.ok, "reason_code": result.reason_code},
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

    1. `{"type": "hello", "token": <session_token>, "client": {...}, "format": "webm" | "mp4" | "h264" | "jpeg"}`
       (`jpeg` when omitted)
    2. <- `{"type": "plan", "challenges": [...], "flash_colors": [...], "flash_hold_ms": n, "oval": {...} | null,
             "client_config": {...}}`
    3. binary messages: 8-byte big-endian device time in ms, then the payload: a video chunk (`webm`, `mp4`:
       MediaRecorder's chunks; `h264`: one Annex-B access unit) stamped with its first frame's time, or one
       JPEG (`jpeg`); sent continuously
       text events: `{"type": "event", "name": "aligned" | "challenge_done" | "flash" | "flash_end", "index"?: i, "ts": ms}`
    4. `{"type": "end"}` -> <- `{"type": "result", ...}` and the socket closes.
    Video is decoded into frames with both clocks (`services/video.py`) before the pipeline runs, so the
    verdict is judged the same way whatever the device sent. The server clocks everything itself; the
    session is spent as soon as the hello is accepted.
    """
    s = get_settings()
    await ws.accept()
    frames: list[StreamFrame] = []
    chunks: list[VideoChunk] = []
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
        fmt = hello.get("format", "jpeg")
        if fmt not in FORMATS:
            raise _StreamError("HELLO_INVALID")
        client_info = {**client_info, "format": fmt}
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
            # Claiming the session also drops a reference embedding: from here it lives in this coroutine only
            # (read before the commit expires the row).
            reference_blob = sess.reference_embedding
            claimed = db.exec(update(VerifySession).where(col(VerifySession.id) == session_id,
                                                          col(VerifySession.used) == False)  # noqa: E712
                              .values(used=True, reference_embedding=None))
            db.commit()
            if claimed.rowcount != 1:
                raise _StreamError("SESSION_USED")
            reference_embedding = np.frombuffer(reference_blob, dtype=np.float32) if reference_blob is not None else None
            challenges = sess.challenges.split(",")
            flash_colors = [c for c in sess.flash_colors.split(",") if c]
            deadline = _now_ms() + int((sess.expires_at - utcnow()).total_seconds() * 1000)
            project_id, purpose, is_reference = project.id, sess.purpose, sess.reference
        p = get_policy()

        await ws.send_json({"type": "plan", "challenges": challenges, "flash_colors": flash_colors,
                            "flash_hold_ms": p.flash_hold_ms, "oval": oval_for(challenges),
                            "client_config": p.client.model_dump()})

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
                if total_bytes > s.max_upload_bytes or len(frames) + len(chunks) >= s.max_stream_chunks:
                    raise _StreamError("PAYLOAD_TOO_LARGE", 1009)
                client_ms = int.from_bytes(data[:8], "big")
                if fmt == "jpeg":
                    frames.append(StreamFrame(recv_ms=now, client_ms=client_ms, data=data[8:]))
                else:
                    chunks.append(VideoChunk(recv_ms=now, client_ms=client_ms, data=data[8:]))
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

        if chunks:
            frames = await asyncio.to_thread(decode_chunks, fmt, chunks, s.max_stream_frames)
        result = await asyncio.to_thread(analyze_stream, frames, events, challenges, flash_colors, reference_embedding)
        if s.store_frames and (s.debug or not result.ok):
            await asyncio.to_thread(_store_frames, project_id, session_id, frames, events, challenges, flash_colors,
                                    reference_embedding, client_info, result, fmt, chunks)
        t0 = frames[0].recv_ms if frames else 0
        with Session(get_engine()) as db:
            row = Verification(project_id=project_id, reference=is_reference, purpose=purpose, session_id=session_id,
                               ok=result.ok, reason_code=result.reason_code,
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
