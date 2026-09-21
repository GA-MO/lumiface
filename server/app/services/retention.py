"""Retention: drop spent sessions on a timer. Nothing biometric outlives a session (see models.VerifySession)."""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import Session, col, delete

from ..config import get_settings
from ..db import get_engine
from ..models import VerifySession, utcnow

log = logging.getLogger("lumiface.retention")


def purge(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Delete sessions past `session_purge_grace_seconds`.

    A session is single use and expires within a minute; the grace keeps the row a little longer
    so a late verify still gets SESSION_EXPIRED rather than SESSION_NOT_FOUND.
    """
    now = now or utcnow()
    grace = timedelta(seconds=get_settings().session_purge_grace_seconds)
    sessions = db.exec(delete(VerifySession).where(col(VerifySession.expires_at) < now - grace))
    db.commit()
    counts = {"sessions": sessions.rowcount}
    if counts["sessions"]:
        log.info("purged %d spent session(s)", counts["sessions"])
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
