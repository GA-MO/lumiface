from pathlib import Path

import numpy as np
import pytest

from app.services.challenge import new_challenges
from app.services.expression import mouth_metrics, smile_ok
from app.services.face import FaceResult
from app.services.flash import PALETTE, face_patch_mean_rgb, flash_passes, score_flash, surroundings_mean_rgb
from app.services.stream import StreamEvent, blink_observed, build_windows, eye_aspect_ratio
from app.services.verify import _pose_ok

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_new_challenges_from_pool(monkeypatch):
    from app.policy import default_policy
    monkeypatch.setattr(default_policy(), "challenge_pool", "blink,smile")
    for _ in range(20):
        c = new_challenges()
        assert len(c) == 2 and len(set(c)) == 2 and set(c) <= {"blink", "smile"}


def test_new_challenges_always_include_required(monkeypatch):
    from app.policy import default_policy
    monkeypatch.setattr(default_policy(), "challenge_pool", "blink,turn_left,turn_right,smile,nod")
    firsts = set()
    for _ in range(40):
        c = new_challenges()
        assert "smile" in c and len(c) == 2
        firsts.add(c[0])
    assert len(firsts) > 1, "required challenge must not always come first"


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


def _eyes(open_ratio):
    """68-point landmarks with both eyes `open_ratio` as tall as they are wide (iBUG 36-47)."""
    pts = np.zeros((68, 3), dtype=np.float32)
    for base, cx in ((36, 40.0), (42, 80.0)):
        pts[base] = (cx - 10, 50, 0)
        pts[base + 3] = (cx + 10, 50, 0)
        h = 20 * open_ratio / 2
        pts[base + 1] = (cx - 4, 50 - h, 0)
        pts[base + 2] = (cx + 4, 50 - h, 0)
        pts[base + 5] = (cx - 4, 50 + h, 0)
        pts[base + 4] = (cx + 4, 50 + h, 0)
    return pts


def test_eye_aspect_ratio_tracks_openness():
    assert eye_aspect_ratio(_eyes(0.3)) == pytest.approx(0.3)
    assert eye_aspect_ratio(_eyes(0.1)) == pytest.approx(0.1)
    assert eye_aspect_ratio(None) is None


def test_blink_needs_a_close_and_a_reopen():
    assert blink_observed([0.3, 0.29, 0.12, 0.28, 0.3], 0.3)
    assert not blink_observed([0.3, 0.3, 0.31, 0.29], 0.3), "eyes never closed"
    assert not blink_observed([0.3, 0.15, 0.12, 0.1], 0.3), "closed and stayed closed"
    assert not blink_observed([0.1, 0.3], 0.0)


def _events(*names):
    out, t = [], 1000
    counts: dict[str, int] = {}
    for n in names:
        idx = None
        if n in ("challenge_done", "flash"):
            idx = counts.get(n, 0)
            counts[n] = idx + 1
        out.append(StreamEvent(name=n, recv_ms=t, index=idx))
        t += 500
    return out


def test_windows_follow_the_plan_on_the_server_clock():
    w = build_windows(_events("aligned", "challenge_done", "challenge_done", "flash", "flash", "flash_end", "end"),
                      first_frame_ms=200, challenges=["blink", "smile"], flash_colors=["FF0000", "00FF00"])
    assert w.align == (200, 1000)
    assert w.challenges == [(1000, 1500), (1500, 2000)]
    assert w.flashes == [(2500 + 120, 3000), (3000 + 120, 3500)]
    assert w.end == (3500, 4000)


def test_windows_reject_a_wrong_or_reordered_sequence():
    assert build_windows(_events("aligned", "end"), 0, ["blink"], []) == "TIMING_ORDER"
    assert build_windows(_events("challenge_done", "aligned", "end"), 0, ["blink"], []) == "TIMING_ORDER"
    bad = _events("aligned", "challenge_done", "challenge_done", "end")
    bad[2].index = 0  # the same challenge reported twice
    assert build_windows(bad, 0, ["blink", "smile"], []) == "TIMING_ORDER"
    late = _events("aligned", "challenge_done", "end")
    late[1].recv_ms = 100  # earlier than the event before it
    assert build_windows(late, 0, ["blink"], []) == "TIMING_ORDER"
    w = build_windows(_events("aligned", "challenge_done", "end"), 0, ["blink"], [])
    assert w.flashes == [] and w.end == (1500, 2000)


def _face(yaw=0.0, pitch=0.0):
    return FaceResult(bbox=np.array([0, 0, 200, 200], dtype=np.float32), det_score=0.9, pitch=pitch, yaw=yaw,
                      roll=0.0, embedding=np.zeros(512, dtype=np.float32))


def test_pose_checks_strict_direction(monkeypatch):
    from app.policy import default_policy
    monkeypatch.setattr(default_policy(), "turn_strict_direction", True)
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
