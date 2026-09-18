from pathlib import Path

import numpy as np
import pytest

from app.services.challenge import VerifyMeta, expected_frame_kinds, new_challenges, validate_timing
from app.services.expression import mouth_metrics, smile_ok
from app.services.face import FaceResult
from app.services.flash import PALETTE, face_patch_mean_rgb, flash_passes, score_flash, surroundings_mean_rgb
from app.services.verify import _pose_ok
from tests.conftest import make_meta

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_new_challenges_from_pool():
    for _ in range(20):
        c = new_challenges()
        assert len(c) == 2 and len(set(c)) == 2 and set(c) <= {"blink", "smile"}


def test_new_challenges_always_include_required(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "challenge_pool", "blink,turn_left,turn_right,smile,nod")
    firsts = set()
    for _ in range(40):
        c = new_challenges()
        assert "smile" in c and len(c) == 2
        firsts.add(c[0])
    assert len(firsts) > 1, "required challenge must not always come first"


def test_expected_frame_kinds():
    assert expected_frame_kinds(["blink", "smile"]) == ["neutral_start", "challenge_0", "challenge_1", "neutral_end"]
    assert expected_frame_kinds(["blink"], ["FF0000", "0000FF"]) == \
        ["neutral_start", "challenge_0", "flash_0", "flash_1", "neutral_end"]


def _lit(base, colors, gain, noise=0.0, seed=0):
    """Face patch means for a surface reflecting `gain` * commanded colour on top of `base`."""
    rng = np.random.default_rng(seed)
    return [np.asarray(base, dtype=np.float32) + gain * np.asarray(PALETTE[c], dtype=np.float32)
            + rng.normal(0, noise, 3).astype(np.float32) for c in colors]


def test_flash_real_face_follows_sequence():
    colors = ["FF0000", "00FF00", "0000FF"]
    r = score_flash(_lit((150, 120, 110), colors, gain=6, noise=0.5), colors)
    assert r.correlation > 0.9 and r.response > 2 and r.order_ok
    assert flash_passes(r)


def test_flash_screen_replay_reflects_nothing():
    colors = ["FF00FF", "00FFFF", "FFFF00"]
    r = score_flash(_lit((150, 120, 110), colors, gain=0, noise=0.3), colors)
    assert r.response < 1 and not flash_passes(r)


def test_flash_glossy_screen_replay_reflects_everywhere():
    colors = ["FF0000", "00FF00", "0000FF"]
    face = _lit((150, 120, 110), colors, gain=8)
    real = score_flash(face, colors, _lit((90, 90, 90), colors, gain=4))
    assert real.background_ratio is not None and abs(real.background_ratio - 0.5) < 0.05 and flash_passes(real)
    replay = score_flash(face, colors, _lit((90, 90, 90), colors, gain=10))
    assert replay.correlation > 0.9 and replay.background_ratio > 1.0 and not flash_passes(replay)


def test_surroundings_ring_excludes_face():
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)             # BGR red everywhere
    img[100:200, 100:200] = (255, 0, 0)  # blue face box
    rgb = surroundings_mean_rgb(img, (100, 100, 200, 200))
    assert rgb[0] > 200 and rgb[2] < 50, "ring must be the red surroundings, not the blue face"


def test_flash_wrong_order_is_rejected():
    colors = ["FF0000", "00FF00", "0000FF"]
    obs = _lit((150, 120, 110), ["0000FF", "FF0000", "00FF00"], gain=6)
    r = score_flash(obs, colors)
    assert not r.order_ok and r.correlation < 0.5 and not flash_passes(r)


def test_flash_ignores_global_exposure_drift():
    colors = ["FF0000", "00FF00", "0000FF"]
    obs = [v + 20 * i for i, v in enumerate(_lit((150, 120, 110), colors, gain=8))]
    r = score_flash(obs, colors)
    assert r.correlation > 0.6 and r.order_ok


def _landmarks(mouth_w=60.0, lift=0.0):
    """68 points with eyes 100 px apart; mouth corners `mouth_w` apart, `lift` px above the lip centre."""
    pts = np.zeros((68, 3), dtype=np.float32)
    pts[36] = (0, 0, 0)
    pts[45] = (100, 0, 0)
    pts[48] = (50 - mouth_w / 2, 60 - lift, 0)
    pts[54] = (50 + mouth_w / 2, 60 - lift, 0)
    pts[51] = (50, 55, 0)
    pts[57] = (50, 65, 0)
    return pts


def test_smile_metrics_and_decision():
    neutral = mouth_metrics(_landmarks())
    assert neutral is not None and abs(neutral.width - 0.6) < 1e-6 and abs(neutral.lift) < 1e-6
    ok, info = smile_ok(neutral, mouth_metrics(_landmarks(mouth_w=69, lift=7)))
    assert ok and info["width_gain"] > 1.1 and info["lift"] > 0.06
    ok, _ = smile_ok(neutral, mouth_metrics(_landmarks(mouth_w=69)))
    assert ok, "wider mouth alone is enough"
    ok, _ = smile_ok(neutral, mouth_metrics(_landmarks(lift=6)))
    assert ok, "corner lift alone is enough"
    ok, info = smile_ok(neutral, mouth_metrics(_landmarks(mouth_w=61, lift=1)))
    assert not ok, info
    assert smile_ok(None, neutral)[0], "no landmarks -> skip, never reject"


@pytest.mark.skipif(not (SAMPLES / "replay_phone" / "b460f086_neutral_start.jpg").exists(), reason="local samples only")
def test_smile_on_recorded_session_frames():
    from app.services.face import decode_image, get_face_engine

    def metrics(name):
        faces = get_face_engine().analyze(decode_image((SAMPLES / "replay_phone" / name).read_bytes()))
        return mouth_metrics(faces[0].landmarks)

    neutral = metrics("b460f086_neutral_start.jpg")
    assert smile_ok(neutral, metrics("b460f086_challenge_1.jpg"))[0], "genuine smile frame"
    ok, info = smile_ok(metrics("c6f9e2f5_neutral_start.jpg"), metrics("c6f9e2f5_challenge_1.jpg"))
    assert not ok, f"non-smile challenge frame must not pass: {info}"


def _face_emb(vec, yaw=0.0, pitch=0.0):
    e = np.zeros(512, dtype=np.float32)
    e[: len(vec)] = vec
    e /= np.linalg.norm(e)
    return FaceResult(bbox=np.array([0, 0, 200, 200], dtype=np.float32), det_score=0.9, pitch=pitch, yaw=yaw,
                      roll=0.0, embedding=e)


def test_consistency_relaxed_for_pose_frames():
    from app.services.verify import _consistency
    a = _face_emb([1, 0])
    tilted = _face_emb([1, 1], pitch=-40)     # cos 0.71 to a
    far = _face_emb([1, 1.6], pitch=-40)      # cos 0.53 to a
    worst, ok = _consistency([a, tilted, a])
    assert ok and abs(worst - 0.707) < 0.01
    worst, ok = _consistency([a, far, a])
    assert ok, "0.53 is fine for a nod frame"
    worst, ok = _consistency([a, _face_emb([1, 1.6]), a])
    assert not ok, "0.53 between frontal frames is a different person"
    assert not _consistency([a, _face_emb([1, 3], pitch=-40), a])[1], "pose frames still have a floor"


def test_face_patch_mean_rgb_reads_centre_block():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)          # BGR red everywhere
    img[45:65, 35:65] = (255, 0, 0)  # BGR blue in the cheek block
    rgb = face_patch_mean_rgb(img, (20, 20, 80, 80))
    assert rgb[2] > 200 and rgb[0] < 60


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
