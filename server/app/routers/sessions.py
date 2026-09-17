import json
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_db
from ..deps import current_project
from ..models import Checkin, CheckinSession, Employee, Project, utcnow
from ..services.challenge import VerifyMeta, expected_frame_kinds, new_challenges
from ..services.verify import verify

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    employee_id: str | None = None


class SessionOut(BaseModel):
    session_id: str
    challenges: list[str]
    frame_kinds: list[str]
    expires_at: str
    ttl_seconds: int


class Scores(BaseModel):
    match: float | None = None
    spoof: float | None = None
    consistency: float | None = None


class VerifyOut(BaseModel):
    ok: bool
    reason_code: str
    scores: Scores
    checkin_id: int | None = None
    details: dict = {}


@router.post("", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate | None = None, project: Project = Depends(current_project),
                   db: Session = Depends(get_db)):
    s = get_settings()
    challenges = new_challenges()
    sess = CheckinSession(
        id=uuid.uuid4().hex,
        project_id=project.id,
        employee_external_id=body.employee_id if body else None,
        challenges=",".join(challenges),
        expires_at=utcnow() + timedelta(seconds=s.session_ttl_seconds),
    )
    db.add(sess)
    db.commit()
    return SessionOut(session_id=sess.id, challenges=challenges, frame_kinds=expected_frame_kinds(challenges),
                      expires_at=sess.expires_at.isoformat() + "Z", ttl_seconds=s.session_ttl_seconds)


def _store_frames(session_id: str, frames: list[bytes], kinds: list[str]) -> None:
    d = Path(get_settings().frames_dir) / session_id
    d.mkdir(parents=True, exist_ok=True)
    for data, kind in zip(frames, kinds):
        (d / f"{kind}.jpg").write_bytes(data)


@router.post("/{session_id}/verify", response_model=VerifyOut)
async def verify_session(
    session_id: str,
    employee_id: str = Form(...),
    meta: str = Form(...),
    frames: list[UploadFile] = File(...),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    s = get_settings()
    sess = db.get(CheckinSession, session_id)
    if not sess or sess.project_id != project.id:
        raise HTTPException(404, "session not found")
    if sess.used:
        raise HTTPException(409, {"reason_code": "SESSION_USED"})
    if sess.expires_at < utcnow():
        raise HTTPException(410, {"reason_code": "SESSION_EXPIRED"})
    if sess.employee_external_id and sess.employee_external_id != employee_id:
        raise HTTPException(400, {"reason_code": "EMPLOYEE_MISMATCH"})
    emp = db.exec(select(Employee).where(Employee.project_id == project.id,
                                         Employee.external_id == employee_id)).first()
    if not emp:
        raise HTTPException(404, {"reason_code": "EMPLOYEE_NOT_FOUND"})
    try:
        vmeta = VerifyMeta.model_validate(json.loads(meta))
    except (ValidationError, ValueError) as e:
        raise HTTPException(422, {"reason_code": "META_INVALID", "error": str(e)})

    sess.used = True
    db.add(sess)
    db.commit()

    data = [await f.read() for f in frames]
    challenges = sess.challenges.split(",")
    enrolled = np.frombuffer(emp.embedding, dtype=np.float32)
    result = verify(data, vmeta, challenges, enrolled)

    if s.store_frames and (s.debug or not result.ok):
        _store_frames(session_id, data, [m.kind for m in vmeta.frames][: len(data)])

    row = Checkin(project_id=project.id, employee_id=emp.id, employee_external_id=employee_id,
                  session_id=session_id, ok=result.ok, reason_code=result.reason_code,
                  match_score=result.match_score, spoof_score=result.spoof_score,
                  consistency_score=result.consistency_score,
                  details=json.dumps({**result.details, "challenges": challenges, "client": vmeta.client,
                                      "challenge_durations_ms": vmeta.challenge_durations_ms,
                                      "frame_ts_ms": [m.ts_ms for m in vmeta.frames]}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return VerifyOut(ok=result.ok, reason_code=result.reason_code,
                     scores=Scores(match=result.match_score, spoof=result.spoof_score,
                                   consistency=result.consistency_score),
                     checkin_id=row.id if result.ok else None,
                     details=result.details if s.debug else {})
