from datetime import timedelta

import numpy as np
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, col, select

from ..config import get_settings
from ..db import get_db
from ..deps import bearer_token, current_project, new_token, project_for_token, project_from_api_key
from ..models import EnrolToken, Project, Subject, Verification, utcnow
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


class EnrolTokenCreate(BaseModel):
    """Re-enrolment (`replace`) is deliberately not offered here: a device holding a token could
    overwrite an existing face with its own. Delete or re-enrol with the project key instead."""

    external_id: str = Field(min_length=1, max_length=128)
    name: str = Field("", max_length=128)
    ttl_seconds: int | None = Field(None, ge=0, description="Subject retention; omitted uses the policy.")
    token_ttl_seconds: int | None = Field(None, gt=0, le=86400, description="How long the device has to enrol.")


class EnrolTokenOut(BaseModel):
    token: str
    external_id: str
    expires_at: str


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


@router.post("/tokens", response_model=EnrolTokenOut, status_code=201)
def create_enrol_token(body: EnrolTokenCreate, project: Project = Depends(current_project),
                       db: Session = Depends(get_db)):
    """Backend-issued, single-use token a device presents to `POST /v1/subjects` instead of the project key."""
    ttl = body.token_ttl_seconds or get_settings().enrol_token_ttl_seconds
    row = EnrolToken(token=new_token(), project_id=project.id, external_id=body.external_id, name=body.name,
                     ttl_seconds=body.ttl_seconds, expires_at=utcnow() + timedelta(seconds=ttl))
    db.add(row)
    db.commit()
    return EnrolTokenOut(token=row.token, external_id=row.external_id, expires_at=row.expires_at.isoformat() + "Z")


@router.post("", response_model=SubjectOut, status_code=201)
async def enroll_subject(
    photo: UploadFile = File(...),
    external_id: str | None = Form(None),
    name: str | None = Form(None),
    replace: bool | None = Form(None),
    ttl_seconds: int | None = Form(None, description="Retention in seconds; 0 keeps it, omitted uses the policy."),
    token: str | None = Depends(bearer_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    ticket: EnrolToken | None = None
    if token is not None:
        # The device holds an enrol token: who gets enrolled was fixed by the backend that issued it.
        # Claim it atomically so two uploads with the same token cannot both get through.
        claimed = db.exec(update(EnrolToken).where(col(EnrolToken.token) == token, col(EnrolToken.used) == False,  # noqa: E712
                                                   col(EnrolToken.expires_at) > utcnow()).values(used=True))
        db.commit()
        if claimed.rowcount != 1:
            raise HTTPException(401, {"reason_code": "ENROL_TOKEN_INVALID"})
        ticket = db.get(EnrolToken, token)
        try:
            for given, fixed in ((external_id, ticket.external_id), (name, ticket.name)):
                if given is not None and given != fixed:
                    raise HTTPException(403, {"reason_code": "ENROL_TOKEN_MISMATCH"})
            if replace or ttl_seconds is not None and ttl_seconds != ticket.ttl_seconds:
                raise HTTPException(403, {"reason_code": "ENROL_TOKEN_MISMATCH"})
            project = project_for_token(db, ticket.project_id)
        except HTTPException:
            _release(db, ticket)
            raise
        external_id, name, replace, ttl_seconds = ticket.external_id, ticket.name, False, ticket.ttl_seconds
    else:
        project = project_from_api_key(db, x_api_key)
        if not external_id:
            raise HTTPException(422, {"reason_code": "EXTERNAL_ID_REQUIRED"})
    name = name or ""
    replace = bool(replace)
    expires_at = _expiry(ttl_seconds)
    existing = find_subject(db, project, external_id, include_expired=True)
    if existing and not existing.expired and not replace:
        _release(db, ticket)
        raise HTTPException(409, {"reason_code": "SUBJECT_EXISTS", "detail": "pass replace=true to re-enrol"})
    data = await photo.read()
    if len(data) > get_settings().max_frame_bytes:
        _release(db, ticket)
        raise HTTPException(413, {"reason_code": "PAYLOAD_TOO_LARGE"})
    result = enroll(data)
    if not result.ok:
        # A rejected photo (no face, spoof, pose) hands the token back so the device can retry until it expires.
        _release(db, ticket)
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


def _release(db: Session, ticket: EnrolToken | None) -> None:
    if ticket is not None:
        ticket.used = False
        db.add(ticket)
        db.commit()


def unlink_verifications(db: Session, subject_ids: list[int]) -> None:
    """Keep the audit log, drop the link to the embedding that is going away."""
    if subject_ids:
        db.exec(update(Verification).where(col(Verification.subject_id).in_(subject_ids)).values(subject_id=None))


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
    unlink_verifications(db, [row.id])
    db.delete(row)
    db.commit()
