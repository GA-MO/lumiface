
import numpy as np
import pytest

from app.services.challenge import new_challenges, oval_for
from app.services.face import FaceResult
from app.services.flash import PALETTE, face_patch_mean_rgb, flash_passes, score_flash, surroundings_mean_rgb
from app.services.stream import Analysed, StreamEvent, StreamFrame, build_windows, movement_observed, placement_windows


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
                      first_frame_ms=200, challenges=["face_move", "face_move"], flash_colors=["FF0000", "00FF00"])
    assert w.align == (200, 1000)
    assert w.challenges == [(1000, 1500), (1500, 2000)]
    assert w.flashes == [(2500 + 120, 3000), (3000 + 120, 3500)]
    assert w.end == (3500, 4000)


def test_windows_reject_a_wrong_or_reordered_sequence():
    assert build_windows(_events("aligned", "end"), 0, ["face_move"], []) == "TIMING_ORDER"
    assert build_windows(_events("challenge_done", "aligned", "end"), 0, ["face_move"], []) == "TIMING_ORDER"
    bad = _events("aligned", "challenge_done", "challenge_done", "end")
    bad[2].index = 0  # the same challenge reported twice
    assert build_windows(bad, 0, ["face_move", "face_move"], []) == "TIMING_ORDER"
    late = _events("aligned", "challenge_done", "end")
    late[1].recv_ms = 100  # earlier than the event before it
    assert build_windows(late, 0, ["face_move"], []) == "TIMING_ORDER"
    w = build_windows(_events("aligned", "challenge_done", "end"), 0, ["face_move"], [])
    assert w.flashes == [] and w.end == (1500, 2000)


def test_frames_are_placed_on_the_device_clock_when_it_is_stamped():
    events = _events("aligned", "challenge_done", "flash", "flash_end", "end")
    for e in events[:-1]:
        e.client_ms = e.recv_ms - 300  # every event reaches the server 300 ms after the device raised it
    frames = [StreamFrame(recv_ms=t + 300, client_ms=t, data=b"") for t in range(0, 2500, 100)]
    server = build_windows(events, 300, ["face_move"], ["FF0000"])
    place = placement_windows(frames, events, ["face_move"], ["FF0000"], server)
    assert place is not server
    assert place.align == (0, 700) and place.challenges == [(700, 1200)]
    assert place.flashes == [(1700 + 120, 2200)] and place.end == (2200, 2400)
    events[1].client_ms = None
    assert placement_windows(frames, events, ["face_move"], ["FF0000"], server) is server


def _analysed(width_px: int, cx: int = 320, img_w: int = 640, t: int = 0) -> Analysed:
    bbox = np.array([cx - width_px / 2, 100, cx + width_px / 2, 100 + width_px * 1.3], dtype=np.float32)
    face = FaceResult(bbox=bbox, det_score=0.9, pitch=0.0, yaw=0.0, roll=0.0, embedding=np.zeros(512, dtype=np.float32))
    return Analysed(StreamFrame(recv_ms=t, client_ms=t, data=b""), face, None, np.zeros((480, img_w, 3), dtype=np.uint8))


def test_face_move_wants_the_face_to_grow_into_the_oval(monkeypatch):
    from app.policy import default_policy
    s = default_policy()
    monkeypatch.setattr(s, "oval_width_fraction", 0.62)
    far, near = _analysed(160), _analysed(380)  # 0.25 -> 0.59 of a 640 px frame, oval 0.62
    ok, info, peak = movement_observed([far, far, _analysed(220), _analysed(300), near, near], s)
    assert ok and peak is near and info["growth"] > 2 and info["fill"] > 0.9
    ok, info, _ = movement_observed([near, near, near, near], s)
    assert not ok and info["growth"] == 1.0, "already close: no movement seen"
    ok, info, _ = movement_observed([far, far, _analysed(220), _analysed(220)], s)
    assert not ok and info["fill"] < 0.75, "moved but never filled the oval"
    ok, info, _ = movement_observed([near, near, _analysed(200), far, _analysed(300), near, near], s)
    assert ok and info["growth"] > 2, "aligned close, backed off, then walked in: the start is the farthest frame"
    ok, info, _ = movement_observed([far, far, _analysed(380, cx=80), _analysed(380, cx=80)], s)
    assert not ok and not info["centred"], "filled the width off to the side"


def test_plan_is_the_oval_alone():
    assert new_challenges() == ["face_move"]
    assert oval_for(["face_move"]) == {"cx": 0.5, "cy": 0.45, "width": 0.35, "height_ratio": 1.35}
    assert oval_for([]) is None


def test_analysis_pool_is_sized_from_the_cores(monkeypatch):
    from app.config import get_settings
    from app.services import inference

    s = get_settings()
    monkeypatch.setattr(inference.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(s, "inference_threads", 2)
    monkeypatch.setattr(s, "max_concurrent_analyses", 0)
    monkeypatch.setattr(s, "max_open_streams", 0)
    assert inference.analysis_slots() == 1 and inference.open_stream_slots() == 4
    monkeypatch.setattr(inference.os, "cpu_count", lambda: 10)
    assert inference.analysis_slots() == 5 and inference.open_stream_slots() == 20
    monkeypatch.setattr(s, "max_concurrent_analyses", 3)
    monkeypatch.setattr(s, "max_open_streams", 7)
    assert inference.analysis_slots() == 3 and inference.open_stream_slots() == 7
    assert inference.session_options().intra_op_num_threads == 2
