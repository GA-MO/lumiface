"""Server-side challenge selection."""
from __future__ import annotations

import secrets

from ..policy import get_policy

ALL_CHALLENGES = ("blink", "turn_left", "turn_right", "smile", "nod")


def new_challenges() -> list[str]:
    s = get_policy()
    pool = [c for c in s.challenges if c in ALL_CHALLENGES]
    n = min(s.challenge_count, len(pool))
    picked: list[str] = []
    # A rigid mask (latex/silicone) passes both passive gates; it cannot smile.
    if s.required_challenge in pool and n > 0:
        picked.append(s.required_challenge)
    while len(picked) < n:
        c = secrets.choice(pool)
        if c not in picked:
            picked.append(c)
    secrets.SystemRandom().shuffle(picked)
    return picked
