"""Retention: drop expired subjects (biometric data) and spent sessions on a timer."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from ..config import get_settings
from ..db import get_engine
from ..models import Subject, Verification, VerifySession, utcnow

log = logging.getLogger("lumiface.retention")


def purge(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Delete expired subjects and sessions past `session_purge_grace_seconds`.

    A session is single use and expires within a minute; the grace keeps the row a little longer
    so a late verify still gets SESSION_EXPIRED rather than SESSION_NOT_FOUND.
    """
    now = now or utcnow()
    grace = timedelta(seconds=get_settings().session_purge_grace_seconds)
    expired_ids = db.exec(select(Subject.id).where(col(Subject.expires_at) < now)).all()
    if expired_ids:
        # Keep the audit log; only the link to the deleted embedding goes.
        db.exec(update(Verification).where(col(Verification.subject_id).in_(expired_ids)).values(subject_id=None))
        db.exec(delete(Subject).where(col(Subject.id).in_(expired_ids)))
    sessions = db.exec(delete(VerifySession).where(col(VerifySession.expires_at) < now - grace))
    db.commit()
    counts = {"subjects": len(expired_ids), "sessions": sessions.rowcount}
    if counts["subjects"] or counts["sessions"]:
        log.info("purged %d expired subject(s), %d spent session(s)", counts["subjects"], counts["sessions"])
    return counts


def purge_once() -> dict[str, int]:
    with Session(get_engine()) as db:
        return purge(db)


async def retention_loop() -> None:
    interval = get_settings().retention_interval_seconds
    while True:
        try:
            await asyncio.to_thread(purge_once)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("retention purge failed")
        await asyncio.sleep(interval)
