from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_db
from ..deps import current_project
from ..models import Checkin, Project

router = APIRouter(prefix="/v1/checkins", tags=["checkins"])


class CheckinOut(BaseModel):
    id: int
    employee_id: str
    ok: bool
    reason_code: str
    match_score: float | None
    spoof_score: float | None
    consistency_score: float | None
    created_at: str


@router.get("", response_model=list[CheckinOut])
def list_checkins(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    employee_id: str | None = None,
    ok: bool | None = None,
    limit: int = Query(default=100, le=1000),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    q = select(Checkin).where(Checkin.project_id == project.id)
    if from_:
        q = q.where(Checkin.created_at >= from_)
    if to:
        q = q.where(Checkin.created_at <= to)
    if employee_id:
        q = q.where(Checkin.employee_external_id == employee_id)
    if ok is not None:
        q = q.where(Checkin.ok == ok)
    rows = db.exec(q.order_by(Checkin.created_at.desc()).limit(limit)).all()
    return [CheckinOut(id=r.id, employee_id=r.employee_external_id, ok=r.ok, reason_code=r.reason_code,
                       match_score=r.match_score, spoof_score=r.spoof_score,
                       consistency_score=r.consistency_score, created_at=r.created_at.isoformat() + "Z")
            for r in rows]
