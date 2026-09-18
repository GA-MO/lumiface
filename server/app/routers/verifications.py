from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_db
from ..deps import current_project
from ..models import Project, Verification

router = APIRouter(prefix="/v1/verifications", tags=["verifications"])


class VerificationOut(BaseModel):
    id: int
    session_id: str
    subject_id: str | None
    purpose: str
    ok: bool
    reason_code: str
    match_score: float | None
    spoof_score: float | None
    consistency_score: float | None
    created_at: str


@router.get("", response_model=list[VerificationOut])
def list_verifications(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    subject_id: str | None = None,
    session_id: str | None = None,
    purpose: str | None = None,
    ok: bool | None = None,
    limit: int = Query(default=100, le=1000),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    q = select(Verification).where(Verification.project_id == project.id)
    if from_:
        q = q.where(Verification.created_at >= from_)
    if to:
        q = q.where(Verification.created_at <= to)
    if subject_id:
        q = q.where(Verification.subject_external_id == subject_id)
    if session_id:
        q = q.where(Verification.session_id == session_id)
    if purpose:
        q = q.where(Verification.purpose == purpose)
    if ok is not None:
        q = q.where(Verification.ok == ok)
    rows = db.exec(q.order_by(Verification.created_at.desc()).limit(limit)).all()
    return [VerificationOut(id=r.id, session_id=r.session_id, subject_id=r.subject_external_id, purpose=r.purpose, ok=r.ok,
                            reason_code=r.reason_code, match_score=r.match_score, spoof_score=r.spoof_score,
                            consistency_score=r.consistency_score, created_at=r.created_at.isoformat() + "Z")
            for r in rows]
