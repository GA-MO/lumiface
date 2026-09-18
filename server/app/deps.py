import secrets

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from .config import get_settings
from .db import get_db
from .models import Project
from .policy import Policy, resolve_policy, use_policy


def project_from_api_key(db: Session, x_api_key: str | None) -> Project:
    if not x_api_key:
        raise HTTPException(401, "missing X-API-Key")
    project = db.exec(select(Project).where(Project.api_key == x_api_key)).first()
    if not project:
        raise HTTPException(401, "invalid api key")
    use_policy(project_policy(project))
    return project


def current_project(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Project:
    """The project secret key. Backend only; devices get a session or enrol token instead."""
    return project_from_api_key(db, x_api_key)


_TOKEN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    """`Authorization: Bearer <token>` if present; other schemes (a proxy's Basic auth) are ignored."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    if not token or len(token) > 128 or not set(token) <= _TOKEN_CHARS:
        raise HTTPException(401, "malformed bearer token")
    return token


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_matches(given: str | None, expected: str | None) -> bool:
    if not given or not expected:
        return False
    return secrets.compare_digest(given.encode("utf-8", "surrogateescape"), expected.encode())


def project_for_token(db: Session, project_id: int) -> Project:
    """The project a device token belongs to; gone (project deleted) reads as an invalid token."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(401, "invalid token")
    use_policy(project_policy(project))
    return project


def project_policy(project: Project) -> Policy:
    return resolve_policy(project.preset, project.policy_overrides)


def admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(403, "ADMIN_API_KEY is not configured on this server")
    if not token_matches(x_admin_key, expected):
        raise HTTPException(401, "invalid admin key")
