from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    api_key_hash: str = Field(index=True, unique=True)
    preset: str = "balanced"
    policy_overrides: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)


class VerifySession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    token: str = ""  # bearer secret handed to the device; only good for this session's verify
    # The reference photo's embedding, when the backend gave one (verify) rather than none (liveness); cleared
    # the moment the stream claims the session, so nothing of the photo outlives the verify. The flag stays.
    reference: bool = False
    reference_embedding: bytes | None = None
    purpose: str = ""
    challenges: str
    flash_colors: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    used: bool = False


class Verification(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    reference: bool = False  # verify (matched against the session's reference photo) rather than liveness only
    purpose: str = ""
    session_id: str = Field(index=True)
    ok: bool
    reason_code: str
    match_score: float | None = None
    spoof_score: float | None = None
    consistency_score: float | None = None
    details: str = "{}"
    created_at: datetime = Field(default_factory=utcnow, index=True)
