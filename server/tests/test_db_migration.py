import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlmodel import Session, select

from app.db import _add_missing_columns, _add_missing_indexes, _drop_old_columns, _drop_old_tables, \
    _hash_plaintext_keys, _migration, _sqlite_pragmas
from app.keys import hash_api_key
from app.models import Project, SQLModel, Verification


def _old_database() -> Path:
    """The schema of a server from before enrolment was removed and keys were hashed."""
    path = Path(tempfile.mkdtemp()) / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE project (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, api_key VARCHAR NOT NULL,
                              created_at DATETIME NOT NULL);
        CREATE UNIQUE INDEX ix_project_api_key ON project (api_key);
        INSERT INTO project (name, api_key, created_at) VALUES ('a', 'change-me', '2026-01-01 00:00:00'),
                                                              ('b', 'lf_sk_second', '2026-01-01 00:00:00');
        CREATE TABLE subject (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, embedding BLOB);
        INSERT INTO subject (project_id, embedding) VALUES (1, x'00');
        CREATE TABLE verification (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
                                   subject_id INTEGER REFERENCES subject (id), subject_external_id VARCHAR,
                                   session_id VARCHAR NOT NULL, ok BOOLEAN NOT NULL, reason_code VARCHAR NOT NULL,
                                   match_score FLOAT, spoof_score FLOAT, consistency_score FLOAT,
                                   details VARCHAR NOT NULL, created_at DATETIME NOT NULL);
        CREATE INDEX ix_verification_subject_id ON verification (subject_id);
        INSERT INTO verification (project_id, subject_id, subject_external_id, session_id, ok, reason_code, details,
                                  created_at)
            VALUES (1, 1, 'emp-1', 'sess-1', 1, 'OK', '{}', '2026-01-01 00:00:00');
    """)
    con.commit()
    con.close()
    return path


def _migrate(engine) -> None:
    SQLModel.metadata.create_all(engine)
    with _migration(engine) as conn:
        _drop_old_tables(conn)
        _add_missing_columns(conn)
        _hash_plaintext_keys(conn)
        _drop_old_columns(conn)
        _add_missing_indexes(conn)


def test_old_database_comes_up_hashed_without_subjects():
    engine = create_engine(f"sqlite:///{_old_database()}")
    event.listen(engine, "connect", _sqlite_pragmas)
    _migrate(engine)

    insp = inspect(engine)
    assert "subject" not in insp.get_table_names()
    assert "api_key" not in {c["name"] for c in insp.get_columns("project")}
    assert not {"subject_id", "subject_external_id"} & {c["name"] for c in insp.get_columns("verification")}
    assert ("session_id",) in {tuple(i["column_names"]) for i in insp.get_indexes("verification")}

    with Session(engine) as db:
        assert db.exec(select(Project).where(Project.api_key_hash == hash_api_key("change-me"))).first().name == "a"
        assert db.exec(select(Project).where(Project.api_key_hash == hash_api_key("lf_sk_second"))).first().name == "b"
        assert all(len(p.api_key_hash) == 64 for p in db.exec(select(Project)).all())
        kept = db.exec(select(Verification)).one()
        assert kept.session_id == "sess-1" and kept.purpose == "" and kept.reference is False
        db.add(Verification(project_id=1, session_id="sess-2", ok=False, reason_code="SPOOF"))
        db.commit()
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    _migrate(engine)
