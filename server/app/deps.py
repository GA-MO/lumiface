from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from .config import get_settings
from .db import get_db
from .keys import hash_api_key, token_matches
from .models import Project
from .policy import Policy, resolve_policy, use_policy


def _local_origin(origin: str) -> bool:
    host = urlsplit(origin).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def project_from_api_key(db: Session, x_api_key: str | None, origin: str | None = None) -> Project:
    if not x_api_key:
        raise HTTPException(401, {"reason_code": "API_KEY_MISSING"})
    project = db.exec(select(Project).where(Project.api_key_hash == hash_api_key(x_api_key))).first()
    if not project:
        raise HTTPException(401, {"reason_code": "API_KEY_INVALID"})
    policy = project_policy(project)
    # Browsers always send Origin on cross-site requests and cannot forge it: a project key arriving
    # from a page that is not localhost has been shipped in a bundle.
    if origin and not _local_origin(origin) and not policy.allow_browser_api_key:
        raise HTTPException(401, {"reason_code": "API_KEY_FROM_BROWSER",
                                  "detail": "the project key must stay on your backend; devices use session tokens"})
    use_policy(policy)
    return project


def current_project(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    origin: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Project:
    """The project secret key. Backend only; devices get a session token instead."""
    return project_from_api_key(db, x_api_key, origin)


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
        raise HTTPException(401, {"reason_code": "TOKEN_INVALID"})
    return token


def project_for_token(db: Session, project_id: int) -> Project:
    """The project a device token belongs to; gone (project deleted) reads as an invalid token."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(401, {"reason_code": "TOKEN_INVALID"})
    use_policy(project_policy(project))
    return project


def project_policy(project: Project) -> Policy:
    return resolve_policy(project.preset, project.policy_overrides)


def admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(403, {"reason_code": "ADMIN_KEY_UNSET", "detail": "ADMIN_API_KEY is not configured on this server"})
    if not token_matches(x_admin_key, expected):
        raise HTTPException(401, {"reason_code": "ADMIN_KEY_INVALID"})
