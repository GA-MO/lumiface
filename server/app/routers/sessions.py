import json
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import update
from sqlmodel import Session, col, select

from ..config import get_settings
from ..db import get_db
from ..deps import bearer_token, current_project, new_token, project_for_token, project_from_api_key, token_matches
from ..models import Project, Verification, VerifySession, utcnow
from ..policy import ClientPolicy, get_policy
from ..services.challenge import VerifyMeta, expected_frame_kinds, new_challenges
from ..services.flash import new_flash_colors
from ..services.verify import verify
from .subjects import find_subject

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

PURPOSE_MAX = 40


class SessionCreate(BaseModel):
    subject_id: str | None = None
    purpose: str = Field("", max_length=PURPOSE_MAX)


class SessionOut(BaseModel):
    session_id: str
    session_token: str
    mode: str
    purpose: str
    challenges: list[str]
    flash_colors: list[str]
    frame_kinds: list[str]
    expires_at: str
    ttl_seconds: int
    flash_hold_ms: int
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
    challenges = new_challenges()
    flash_colors = new_flash_colors()
    sess = VerifySession(
        id=uuid.uuid4().hex,
        project_id=project.id,
        token=new_token(),
        subject_external_id=body.subject_id,
        purpose=body.purpose,
        challenges=",".join(challenges),
        flash_colors=",".join(flash_colors),
        expires_at=utcnow() + timedelta(seconds=p.session_ttl_seconds),
    )
    db.add(sess)
    db.commit()
    return SessionOut(session_id=sess.id, session_token=sess.token, mode=_mode(body.subject_id), purpose=body.purpose,
                      challenges=challenges, flash_colors=flash_colors,
                      frame_kinds=expected_frame_kinds(challenges, flash_colors),
                      expires_at=sess.expires_at.isoformat() + "Z", ttl_seconds=p.session_ttl_seconds,
                      flash_hold_ms=p.flash_hold_ms, client_config=p.client)


def _store_frames(project_id: int, session_id: str, frames: list[bytes], kinds: list[str]) -> None:
    """Debug aid. Names come from the server's expected kinds, never from the upload."""
    root = Path(get_settings().frames_dir).resolve()
    d = root / str(project_id) / session_id
    d.mkdir(parents=True, exist_ok=True)
    for i, (data, kind) in enumerate(zip(frames, kinds)):
        target = (d / f"{i:02d}_{kind}.jpg").resolve()
        if target.parent != d.resolve():
            raise ValueError("frame path escaped frames_dir")
        target.write_bytes(data)


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


@router.post("/{session_id}/verify", response_model=VerifyOut)
async def verify_session(
    session_id: str,
    meta: str = Form(...),
    frames: list[UploadFile] = File(...),
    subject_id: str | None = Form(None),
    token: str | None = Depends(bearer_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    s = get_settings()
    sess = db.get(VerifySession, session_id)
    # The device authenticates with the session's own token; a backend may still use the project key.
    if token is not None:
        if not sess or not token_matches(token, sess.token):
            raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
        project = project_for_token(db, sess.project_id)
    else:
        project = project_from_api_key(db, x_api_key)
        if not sess or sess.project_id != project.id:
            raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
    if sess.expires_at < utcnow():
        raise HTTPException(410, {"reason_code": "SESSION_EXPIRED"})
    # Claim the session atomically and before any further check: a token buys exactly one attempt,
    # not a loop of probes, and two concurrent uploads cannot both be scored.
    claimed = db.exec(update(VerifySession).where(col(VerifySession.id) == session_id,
                                                  col(VerifySession.used) == False).values(used=True))  # noqa: E712
    db.commit()
    if claimed.rowcount != 1:
        raise HTTPException(409, {"reason_code": "SESSION_USED"})

    if token is not None:
        # The device does not get to choose whom it is matched against; the backend fixed that at creation.
        if subject_id is not None and subject_id != sess.subject_external_id:
            raise HTTPException(400, {"reason_code": "SUBJECT_MISMATCH"})
        subject_id = sess.subject_external_id
    else:
        subject_id = subject_id or sess.subject_external_id
        if sess.subject_external_id and sess.subject_external_id != subject_id:
            raise HTTPException(400, {"reason_code": "SUBJECT_MISMATCH"})
    subject = find_subject(db, project, subject_id) if subject_id else None
    if subject_id and not subject:
        raise HTTPException(404, {"reason_code": "SUBJECT_NOT_FOUND"})
    try:
        vmeta = VerifyMeta.model_validate(json.loads(meta))
    except ValidationError as e:
        raise HTTPException(422, {"reason_code": "META_INVALID",
                                  "errors": e.errors(include_url=False, include_input=False)})
    except ValueError:
        raise HTTPException(422, {"reason_code": "META_INVALID", "errors": [{"msg": "meta is not JSON"}]})

    challenges = sess.challenges.split(",")
    flash_colors = [c for c in sess.flash_colors.split(",") if c]
    expected_kinds = expected_frame_kinds(challenges, flash_colors)
    if len(frames) > len(expected_kinds):
        raise HTTPException(422, {"reason_code": "FRAME_COUNT"})
    data = []
    for f in frames:
        chunk = await f.read(s.max_frame_bytes + 1)
        if len(chunk) > s.max_frame_bytes:
            raise HTTPException(413, {"reason_code": "PAYLOAD_TOO_LARGE"})
        data.append(chunk)
    enrolled = np.frombuffer(subject.embedding, dtype=np.float32) if subject else None
    result = verify(data, vmeta, challenges, enrolled, flash_colors)

    if s.store_frames and (s.debug or not result.ok):
        _store_frames(project.id, session_id, data, expected_kinds)

    row = Verification(project_id=project.id, subject_id=subject.id if subject else None,
                       subject_external_id=subject_id, purpose=sess.purpose,
                       session_id=session_id, ok=result.ok, reason_code=result.reason_code,
                       match_score=result.match_score, spoof_score=result.spoof_score,
                       consistency_score=result.consistency_score,
                       details=json.dumps({**result.details, "challenges": challenges, "flash_colors": flash_colors,
                                           "client": vmeta.client,
                                           "challenge_durations_ms": vmeta.challenge_durations_ms,
                                           "frame_ts_ms": [m.ts_ms for m in vmeta.frames]}))
    db.add(row)
    db.commit()
    db.refresh(row)
    # Per-frame scores are a tuning oracle: debug details go to the backend, never to a device.
    return _verify_out(row, result.details if s.debug and token is None else None)
