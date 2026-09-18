from datetime import timedelta

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_db
from ..deps import current_project
from ..models import Project, Subject, utcnow
from ..policy import get_policy
from ..services.verify import enroll

router = APIRouter(prefix="/v1/subjects", tags=["subjects"])


class SubjectOut(BaseModel):
    external_id: str
    name: str
    enroll_spoof_score: float
    created_at: str
    expires_at: str | None


def _out(e: Subject) -> SubjectOut:
    return SubjectOut(external_id=e.external_id, name=e.name, enroll_spoof_score=e.enroll_spoof_score,
                      created_at=e.created_at.isoformat() + "Z",
                      expires_at=e.expires_at.isoformat() + "Z" if e.expires_at else None)


def find_subject(db: Session, project: Project, external_id: str, include_expired: bool = False) -> Subject | None:
    """An expired subject is gone from the API's point of view until the purge removes the row."""
    row = db.exec(select(Subject).where(Subject.project_id == project.id,
                                        Subject.external_id == external_id)).first()
    if row and row.expired and not include_expired:
        return None
    return row


def _expiry(ttl_seconds: int | None):
    ttl = get_policy().subject_ttl_seconds if ttl_seconds is None else ttl_seconds
    if ttl < 0:
        raise HTTPException(422, {"reason_code": "TTL_INVALID", "detail": "ttl_seconds must be >= 0"})
    return utcnow() + timedelta(seconds=ttl) if ttl else None


@router.post("", response_model=SubjectOut, status_code=201)
async def enroll_subject(
    external_id: str = Form(...),
    name: str = Form(""),
    photo: UploadFile = File(...),
    replace: bool = Form(False),
    ttl_seconds: int | None = Form(None, description="Retention in seconds; 0 keeps it, omitted uses the policy."),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    expires_at = _expiry(ttl_seconds)
    existing = find_subject(db, project, external_id, include_expired=True)
    if existing and not existing.expired and not replace:
        raise HTTPException(409, {"reason_code": "SUBJECT_EXISTS", "detail": "pass replace=true to re-enrol"})
    result = enroll(await photo.read())
    if not result.ok:
        raise HTTPException(422, {"reason_code": result.reason_code, "details": result.details})
    assert result.embedding is not None
    blob = result.embedding.astype(np.float32).tobytes()
    if existing:
        existing.name = name or existing.name
        existing.embedding = blob
        existing.enroll_spoof_score = result.spoof_score or 0.0
        existing.expires_at = expires_at
        row = existing
    else:
        row = Subject(project_id=project.id, external_id=external_id, name=name, embedding=blob,
                      enroll_spoof_score=result.spoof_score or 0.0, expires_at=expires_at)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("", response_model=list[SubjectOut])
def list_subjects(project: Project = Depends(current_project), db: Session = Depends(get_db)):
    rows = db.exec(select(Subject).where(Subject.project_id == project.id).order_by(Subject.external_id)).all()
    return [_out(e) for e in rows if not e.expired]


@router.get("/{external_id}", response_model=SubjectOut)
def get_subject(external_id: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    row = find_subject(db, project, external_id)
    if not row:
        raise HTTPException(404, {"reason_code": "SUBJECT_NOT_FOUND"})
    return _out(row)


@router.delete("/{external_id}", status_code=204)
def delete_subject(external_id: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    row = find_subject(db, project, external_id, include_expired=True)
    if not row:
        raise HTTPException(404, {"reason_code": "SUBJECT_NOT_FOUND"})
    db.delete(row)
    db.commit()
