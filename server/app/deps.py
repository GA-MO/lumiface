from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from .config import get_settings
from .db import get_db
from .models import Project
from .policy import Policy, resolve_policy, use_policy


def current_project(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Project:
    if not x_api_key:
        raise HTTPException(401, "missing X-API-Key")
    project = db.exec(select(Project).where(Project.api_key == x_api_key)).first()
    if not project:
        raise HTTPException(401, "invalid api key")
    use_policy(project_policy(project))
    return project


def project_policy(project: Project) -> Policy:
    return resolve_policy(project.preset, project.policy_overrides)


def admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(403, "ADMIN_API_KEY is not configured on this server")
    if x_admin_key != expected:
        raise HTTPException(401, "invalid admin key")
