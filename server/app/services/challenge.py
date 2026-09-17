"""Server-side challenge selection and client timing validation."""
from __future__ import annotations

import secrets

from pydantic import BaseModel, Field

from ..config import get_settings

ALL_CHALLENGES = ("blink", "turn_left", "turn_right", "smile", "nod")


def new_challenges() -> list[str]:
    s = get_settings()
    pool = [c for c in s.challenges if c in ALL_CHALLENGES]
    n = min(s.challenge_count, len(pool))
    picked: list[str] = []
    while len(picked) < n:
        c = secrets.choice(pool)
        if c not in picked:
            picked.append(c)
    return picked


class FrameMeta(BaseModel):
    kind: str  # neutral_start | challenge_<i> | neutral_end
    ts_ms: int


class VerifyMeta(BaseModel):
    frames: list[FrameMeta]
    challenge_durations_ms: list[int] = Field(default_factory=list)
    client: dict = Field(default_factory=dict)


def expected_frame_kinds(challenges: list[str]) -> list[str]:
    return ["neutral_start", *[f"challenge_{i}" for i in range(len(challenges))], "neutral_end"]


def validate_timing(meta: VerifyMeta, challenges: list[str]) -> str | None:
    """Return a reason code when the timings look scripted/replayed, else None."""
    s = get_settings()
    kinds = [f.kind for f in meta.frames]
    if kinds != expected_frame_kinds(challenges):
        return "FRAME_KINDS"
    ts = [f.ts_ms for f in meta.frames]
    if any(b < a for a, b in zip(ts, ts[1:])):
        return "TIMING_ORDER"
    total = ts[-1] - ts[0]
    if total < s.min_session_ms:
        return "TIMING_TOO_FAST"
    if total > s.session_ttl_seconds * 1000:
        return "TIMING_TOO_SLOW"
    if len(meta.challenge_durations_ms) != len(challenges):
        return "TIMING_DURATIONS"
    if any(d < s.min_challenge_ms for d in meta.challenge_durations_ms):
        return "TIMING_TOO_FAST"
    if any(d > s.max_challenge_ms for d in meta.challenge_durations_ms):
        return "TIMING_TOO_SLOW"
    return None
