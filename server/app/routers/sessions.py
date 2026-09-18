import json
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_project
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
        subject_external_id=body.subject_id,
        purpose=body.purpose,
        challenges=",".join(challenges),
        flash_colors=",".join(flash_colors),
        expires_at=utcnow() + timedelta(seconds=p.session_ttl_seconds),
    )
    db.add(sess)
    db.commit()
    return SessionOut(session_id=sess.id, mode=_mode(body.subject_id), purpose=body.purpose,
                      challenges=challenges, flash_colors=flash_colors,
                      frame_kinds=expected_frame_kinds(challenges, flash_colors),
                      expires_at=sess.expires_at.isoformat() + "Z", ttl_seconds=p.session_ttl_seconds,
                      flash_hold_ms=p.flash_hold_ms, client_config=p.client)


def _store_frames(session_id: str, frames: list[bytes], kinds: list[str]) -> None:
    d = Path(get_settings().frames_dir) / session_id
    d.mkdir(parents=True, exist_ok=True)
    for data, kind in zip(frames, kinds):
        (d / f"{kind}.jpg").write_bytes(data)


@router.post("/{session_id}/verify", response_model=VerifyOut)
async def verify_session(
    session_id: str,
    meta: str = Form(...),
    frames: list[UploadFile] = File(...),
    subject_id: str | None = Form(None),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    s = get_settings()
    sess = db.get(VerifySession, session_id)
    if not sess or sess.project_id != project.id:
        raise HTTPException(404, {"reason_code": "SESSION_NOT_FOUND"})
    if sess.used:
        raise HTTPException(409, {"reason_code": "SESSION_USED"})
    if sess.expires_at < utcnow():
        raise HTTPException(410, {"reason_code": "SESSION_EXPIRED"})
    subject_id = subject_id or sess.subject_external_id
    if sess.subject_external_id and sess.subject_external_id != subject_id:
        raise HTTPException(400, {"reason_code": "SUBJECT_MISMATCH"})
    subject = find_subject(db, project, subject_id) if subject_id else None
    if subject_id and not subject:
        raise HTTPException(404, {"reason_code": "SUBJECT_NOT_FOUND"})
    try:
        vmeta = VerifyMeta.model_validate(json.loads(meta))
    except (ValidationError, ValueError) as e:
        raise HTTPException(422, {"reason_code": "META_INVALID", "error": str(e)})

    sess.used = True
    db.add(sess)
    db.commit()

    data = [await f.read() for f in frames]
    challenges = sess.challenges.split(",")
    flash_colors = [c for c in sess.flash_colors.split(",") if c]
    enrolled = np.frombuffer(subject.embedding, dtype=np.float32) if subject else None
    result = verify(data, vmeta, challenges, enrolled, flash_colors)

    if s.store_frames and (s.debug or not result.ok):
        _store_frames(session_id, data, [m.kind for m in vmeta.frames][: len(data)])

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
    return VerifyOut(ok=result.ok, mode=_mode(subject_id), reason_code=result.reason_code,
                     scores=Scores(match=result.match_score, spoof=result.spoof_score,
                                   consistency=result.consistency_score),
                     verification_id=row.id if result.ok else None,
                     details=result.details if s.debug else {})
