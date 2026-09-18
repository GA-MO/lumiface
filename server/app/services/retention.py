"""Retention: drop expired subjects (biometric data) and spent sessions on a timer."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import Session, col, delete, select

from ..config import get_settings
from ..db import get_engine
from ..models import EnrolToken, Subject, VerifySession, utcnow

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
        from ..routers.subjects import unlink_verifications

        unlink_verifications(db, list(expired_ids))
        db.exec(delete(Subject).where(col(Subject.id).in_(expired_ids)))
    sessions = db.exec(delete(VerifySession).where(col(VerifySession.expires_at) < now - grace))
    tokens = db.exec(delete(EnrolToken).where(col(EnrolToken.expires_at) < now - grace))
    db.commit()
    counts = {"subjects": len(expired_ids), "sessions": sessions.rowcount, "enrol_tokens": tokens.rowcount}
    if any(counts.values()):
        log.info("purged %d expired subject(s), %d spent session(s), %d enrol token(s)",
                 counts["subjects"], counts["sessions"], counts["enrol_tokens"])
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
