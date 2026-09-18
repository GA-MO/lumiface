"""Replays stored sessions (`server/data/sessions/{genuine,attack}/<session>/`, kept out of git) through
the pipeline: every genuine session must pass, every attack session must be refused. Skipped where the
folder is absent. Grow the set from `data/frames/<project>/` after each live test (`STORE_FRAMES=1`)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SESSIONS = Path(__file__).resolve().parents[1] / "data" / "sessions"


def _folders(label: str) -> list[Path]:
    d = SESSIONS / label
    return sorted(p for p in d.iterdir() if (p / "session.json").exists()) if d.exists() else []


def _replay(folder: Path):
    from replay_sessions import enrolled_embedding, load

    from app.policy import _RequestPolicy, _current, resolve_policy, use_policy
    from app.services.stream import analyze_stream
    # The balanced preset as shipped, not the relaxed environment the API tests run under; bound to a
    # fresh policy slot and unbound afterwards so the other tests keep their own.
    token = _current.set(_RequestPolicy())
    try:
        use_policy(resolve_policy("balanced", {"flash_enforce": True, "smile_enforce": True, "min_session_ms": 1500,
                                               "min_challenge_ms": 300, "min_face_size": 112, "enroll_max_pitch": 20}))
        frames, events, meta = load(folder)
        return analyze_stream(frames, events, meta["challenges"], meta["flash_colors"],
                              enrolled_embedding(meta.get("subject_id"), None, folder)), meta
    finally:
        _current.reset(token)


@pytest.mark.parametrize("folder", _folders("genuine"), ids=lambda p: p.name[:8])
def test_genuine_session_passes(folder):
    result, meta = _replay(folder)
    assert result.ok, (result.reason_code, json.dumps(result.details)[:400])


@pytest.mark.parametrize("folder", _folders("attack"), ids=lambda p: p.name[:8])
def test_attack_session_is_refused(folder):
    result, meta = _replay(folder)
    assert not result.ok, json.dumps(result.details)[:400]
