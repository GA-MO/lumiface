import numpy as np

from app.services.challenge import VerifyMeta, expected_frame_kinds, new_challenges, validate_timing
from app.services.face import FaceResult
from app.services.verify import _pose_ok
from tests.conftest import make_meta


def test_new_challenges_from_pool():
    for _ in range(20):
        c = new_challenges()
        assert len(c) == 2 and len(set(c)) == 2 and set(c) <= {"blink", "smile"}


def test_expected_frame_kinds():
    assert expected_frame_kinds(["blink", "smile"]) == ["neutral_start", "challenge_0", "challenge_1", "neutral_end"]


def test_timing_ok():
    assert validate_timing(VerifyMeta(**make_meta(["blink", "smile"])), ["blink", "smile"]) is None


def test_timing_too_fast_total():
    m = make_meta(["blink", "smile"], step=100)
    assert validate_timing(VerifyMeta(**m), ["blink", "smile"]) == "TIMING_TOO_FAST"


def test_timing_too_fast_challenge():
    m = make_meta(["blink", "smile"], challenge_ms=50)
    assert validate_timing(VerifyMeta(**m), ["blink", "smile"]) == "TIMING_TOO_FAST"


def test_timing_too_slow_challenge():
    m = make_meta(["blink", "smile"], challenge_ms=9000)
    assert validate_timing(VerifyMeta(**m), ["blink", "smile"]) == "TIMING_TOO_SLOW"


def test_timing_wrong_kinds():
    m = make_meta(["blink"])
    assert validate_timing(VerifyMeta(**m), ["blink", "smile"]) == "FRAME_KINDS"


def test_timing_order():
    m = make_meta(["blink", "smile"])
    m["frames"][2]["ts_ms"] = 0
    assert validate_timing(VerifyMeta(**m), ["blink", "smile"]) == "TIMING_ORDER"


def _face(yaw=0.0, pitch=0.0):
    return FaceResult(bbox=np.array([0, 0, 200, 200], dtype=np.float32), det_score=0.9, pitch=pitch, yaw=yaw,
                      roll=0.0, embedding=np.zeros(512, dtype=np.float32))


def test_pose_checks_strict_direction(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "turn_strict_direction", True)
    assert _pose_ok("turn_right", _face(yaw=45))
    assert not _pose_ok("turn_right", _face(yaw=-45))
    assert _pose_ok("turn_left", _face(yaw=-30))


def test_pose_checks():
    assert _pose_ok("blink", _face())
    assert not _pose_ok("turn_left", _face(yaw=5))
    assert _pose_ok("turn_left", _face(yaw=-30))
    assert _pose_ok("turn_right", _face(yaw=30))
    assert not _pose_ok("nod", _face(pitch=5))
    assert _pose_ok("nod", _face(pitch=-25))
