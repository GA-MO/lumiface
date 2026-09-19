from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
            else:
                Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _sqlite_pragmas)
    return _engine


def _sqlite_pragmas(conn, _record) -> None:
    conn.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    from . import models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)



_ADDED_COLUMNS = {
    "project": {"preset": "VARCHAR NOT NULL DEFAULT 'balanced'", "policy_overrides": "VARCHAR NOT NULL DEFAULT '{}'"},
    "verifysession": {"purpose": "VARCHAR NOT NULL DEFAULT ''", "token": "VARCHAR NOT NULL DEFAULT ''",
                      "reference": "BOOLEAN NOT NULL DEFAULT 0", "reference_embedding": "BLOB"},
    "verification": {"purpose": "VARCHAR NOT NULL DEFAULT ''", "reference": "BOOLEAN NOT NULL DEFAULT 0"},
}
# Enrolment was removed: the server keeps no face between sessions. A database from before drops its
# subjects and enrol tokens on first start, so no embedding lingers in a file nobody reads any more.
_DROPPED_TABLES = ("enroltoken", "subject")


def _add_missing_columns(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in _DROPPED_TABLES:
            if table in insp.get_table_names():
                conn.execute(text(f"DROP TABLE {table}"))
        for table, cols in _ADDED_COLUMNS.items():
            if table not in insp.get_table_names():
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
