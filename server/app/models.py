from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    api_key: str = Field(index=True, unique=True)
    preset: str = "balanced"
    policy_overrides: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)


class Subject(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("project_id", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    external_id: str = Field(index=True)
    name: str = ""
    embedding: bytes
    enroll_spoof_score: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = Field(default=None, index=True)  # None keeps the subject until deleted

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < utcnow()


class VerifySession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    token: str = ""  # bearer secret handed to the device; only good for this session's verify
    subject_external_id: str | None = None
    purpose: str = ""
    challenges: str
    flash_colors: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    used: bool = False


class EnrolToken(SQLModel, table=True):
    """Single-use bearer token letting a device enrol one predetermined subject."""

    token: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    external_id: str
    name: str = ""
    ttl_seconds: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime = Field(index=True)
    used: bool = False


class Verification(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    subject_id: int | None = Field(default=None, foreign_key="subject.id", index=True)
    subject_external_id: str | None = None
    purpose: str = ""
    session_id: str
    ok: bool
    reason_code: str
    match_score: float | None = None
    spoof_score: float | None = None
    consistency_score: float | None = None
    details: str = "{}"
    created_at: datetime = Field(default_factory=utcnow, index=True)
