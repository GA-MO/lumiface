from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from .db import get_db
from .models import Project


def current_project(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Project:
    if not x_api_key:
        raise HTTPException(401, "missing X-API-Key")
    project = db.exec(select(Project).where(Project.api_key == x_api_key)).first()
    if not project:
        raise HTTPException(401, "invalid api key")
    return project
