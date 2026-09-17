from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    api_key: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class Employee(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("project_id", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    external_id: str = Field(index=True)
    name: str = ""
    embedding: bytes
    enroll_spoof_score: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class CheckinSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    employee_external_id: str | None = None
    challenges: str  # comma separated, in order
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    used: bool = False


class Checkin(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    employee_id: int | None = Field(default=None, foreign_key="employee.id", index=True)
    employee_external_id: str
    session_id: str
    ok: bool
    reason_code: str
    match_score: float | None = None
    spoof_score: float | None = None
    consistency_score: float | None = None
    details: str = "{}"
    created_at: datetime = Field(default_factory=utcnow, index=True)
