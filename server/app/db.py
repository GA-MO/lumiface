from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, MetaData, event, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings
from .keys import hash_api_key

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
    with _migration(engine) as conn:
        _drop_old_tables(conn)
        _add_missing_columns(conn)
        _hash_plaintext_keys(conn)
        _drop_old_columns(conn)
        _add_missing_indexes(conn)


_ADDED_COLUMNS = {
    "project": {"preset": "VARCHAR NOT NULL DEFAULT 'balanced'", "policy_overrides": "VARCHAR NOT NULL DEFAULT '{}'",
                "api_key_hash": "VARCHAR NOT NULL DEFAULT ''"},
    "verifysession": {"purpose": "VARCHAR NOT NULL DEFAULT ''", "token": "VARCHAR NOT NULL DEFAULT ''",
                      "reference": "BOOLEAN NOT NULL DEFAULT 0", "reference_embedding": "BLOB"},
    "verification": {"purpose": "VARCHAR NOT NULL DEFAULT ''", "reference": "BOOLEAN NOT NULL DEFAULT 0"},
}
# Enrolment was removed: the server keeps no face between sessions. A database from before drops its
# subjects and enrol tokens on first start, so no embedding lingers in a file nobody reads any more.
_DROPPED_TABLES = ("enroltoken", "subject")


@contextmanager
def _migration(engine) -> Iterator[Connection]:
    """One connection for the whole migration, with SQLite's foreign keys off: the old tables are dropped
    while columns still point at them, and a table is rebuilt to lose such a column."""
    sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        if sqlite:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            yield conn
            conn.commit()
        finally:
            if sqlite:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def _drop_old_tables(conn: Connection) -> None:
    have = inspect(conn).get_table_names()
    for table in _DROPPED_TABLES:
        if table in have:
            conn.execute(text(f"DROP TABLE {table}"))


def _add_missing_columns(conn: Connection) -> None:
    insp = inspect(conn)
    for table, cols in _ADDED_COLUMNS.items():
        if table not in insp.get_table_names():
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _hash_plaintext_keys(conn: Connection) -> None:
    """A database from before keys were hashed holds them in `api_key`; each becomes its digest, and the
    plaintext column goes with the table rebuild, so the key exists nowhere but with the backend that was handed it."""
    if "api_key" not in {c["name"] for c in inspect(conn).get_columns("project")}:
        return
    rows = conn.execute(text("SELECT id, api_key FROM project WHERE api_key_hash = ''")).all()
    for project_id, key in rows:
        if key:
            conn.execute(text("UPDATE project SET api_key_hash = :h WHERE id = :id"),
                         {"h": hash_api_key(key), "id": project_id})


def _drop_old_columns(conn: Connection) -> None:
    """A table with columns the model no longer has is rebuilt from the model (SQLite cannot drop an indexed
    or foreign-key column): the new table takes the rows' remaining columns and the old one's name."""
    insp = inspect(conn)
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in insp.get_table_names():
            continue
        have = [c["name"] for c in insp.get_columns(table.name)]
        keep = [c.name for c in table.columns if c.name in have]
        if set(have) == set(keep):
            continue
        scratch = MetaData()
        for other in SQLModel.metadata.sorted_tables:
            if other is not table:
                other.to_metadata(scratch)
        fresh = table.to_metadata(scratch, name=f"{table.name}__new")
        for index in list(fresh.indexes):
            fresh.indexes.remove(index)
        fresh.create(conn)
        cols = ", ".join(keep)
        conn.execute(text(f"INSERT INTO {fresh.name} ({cols}) SELECT {cols} FROM {table.name}"))
        conn.execute(text(f"DROP TABLE {table.name}"))
        conn.execute(text(f"ALTER TABLE {fresh.name} RENAME TO {table.name}"))


def _add_missing_indexes(conn: Connection) -> None:
    for table in SQLModel.metadata.sorted_tables:
        for index in table.indexes:
            index.create(conn, checkfirst=True)


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
