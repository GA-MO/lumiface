import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_db
from ..deps import current_project
from ..models import Employee, Project
from ..services.verify import enroll

router = APIRouter(prefix="/v1/employees", tags=["employees"])


class EmployeeOut(BaseModel):
    external_id: str
    name: str
    enroll_spoof_score: float
    created_at: str


def _out(e: Employee) -> EmployeeOut:
    return EmployeeOut(external_id=e.external_id, name=e.name, enroll_spoof_score=e.enroll_spoof_score,
                       created_at=e.created_at.isoformat())


@router.post("", response_model=EmployeeOut, status_code=201)
async def enroll_employee(
    external_id: str = Form(...),
    name: str = Form(""),
    photo: UploadFile = File(...),
    replace: bool = Form(False),
    project: Project = Depends(current_project),
    db: Session = Depends(get_db),
):
    existing = db.exec(select(Employee).where(Employee.project_id == project.id,
                                              Employee.external_id == external_id)).first()
    if existing and not replace:
        raise HTTPException(409, "employee exists; pass replace=true to re-enroll")
    result = enroll(await photo.read())
    if not result.ok:
        raise HTTPException(422, {"reason_code": result.reason_code, "details": result.details})
    assert result.embedding is not None
    blob = result.embedding.astype(np.float32).tobytes()
    if existing:
        existing.name = name or existing.name
        existing.embedding = blob
        existing.enroll_spoof_score = result.spoof_score or 0.0
        emp = existing
    else:
        emp = Employee(project_id=project.id, external_id=external_id, name=name, embedding=blob,
                       enroll_spoof_score=result.spoof_score or 0.0)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _out(emp)


@router.get("", response_model=list[EmployeeOut])
def list_employees(project: Project = Depends(current_project), db: Session = Depends(get_db)):
    rows = db.exec(select(Employee).where(Employee.project_id == project.id).order_by(Employee.external_id)).all()
    return [_out(e) for e in rows]


@router.delete("/{external_id}", status_code=204)
def delete_employee(external_id: str, project: Project = Depends(current_project), db: Session = Depends(get_db)):
    emp = db.exec(select(Employee).where(Employee.project_id == project.id,
                                         Employee.external_id == external_id)).first()
    if not emp:
        raise HTTPException(404, "not found")
    db.delete(emp)
    db.commit()
