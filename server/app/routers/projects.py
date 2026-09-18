import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_db
from ..deps import admin_key
from ..models import EnrolToken, Project, Subject, Verification, VerifySession
from ..policy import PRESETS

router = APIRouter(prefix="/v1/projects", tags=["projects"], dependencies=[Depends(admin_key)])


class ProjectCreate(BaseModel):
    name: str
    preset: str = "balanced"


class ProjectOut(BaseModel):
    id: int
    name: str
    preset: str
    created_at: str
    api_key: str | None = None
    subjects: int = 0
    verifications: int = 0


def _out(p: Project, db: Session, api_key: str | None = None) -> ProjectOut:
    subjects = len(db.exec(select(Subject.id).where(Subject.project_id == p.id)).all())
    verifications = len(db.exec(select(Verification.id).where(Verification.project_id == p.id)).all())
    return ProjectOut(id=p.id, name=p.name, preset=p.preset, created_at=p.created_at.isoformat() + "Z",
                      api_key=api_key, subjects=subjects, verifications=verifications)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    if body.preset not in PRESETS:
        raise HTTPException(422, {"reason_code": "UNKNOWN_PRESET", "presets": list(PRESETS)})
    if db.exec(select(Project).where(Project.name == body.name)).first():
        raise HTTPException(409, {"reason_code": "PROJECT_EXISTS"})
    key = secrets.token_urlsafe(24)
    p = Project(name=body.name, api_key=key, preset=body.preset)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p, db, api_key=key)


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return [_out(p, db) for p in db.exec(select(Project).order_by(Project.id)).all()]


@router.post("/{project_id}/rotate-key", response_model=ProjectOut)
def rotate_key(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, {"reason_code": "PROJECT_NOT_FOUND"})
    p.api_key = secrets.token_urlsafe(24)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p, db, api_key=p.api_key)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, {"reason_code": "PROJECT_NOT_FOUND"})
    # Sessions and enrol tokens go too: SQLite reuses ids, so a live token must not outlive its tenant.
    for model in (Verification, VerifySession, EnrolToken, Subject):
        for row in db.exec(select(model).where(model.project_id == p.id)).all():
            db.delete(row)
    db.delete(p)
    db.commit()
