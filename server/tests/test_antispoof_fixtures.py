"""Regression fixtures captured 2026-09-17 through the Android emulator + Mac webcam:
real_webcam_*  = live face; replay_phone_* = a video of the same person played on a phone screen.
They are a person's face, so they live outside the repository (`server/data/fixtures/`, git-ignored like the
replay set) and these tests skip where they are absent (CI)."""
from pathlib import Path

import pytest

from app.policy import default_policy
from app.services.antispoof import get_antispoof
from app.services.face import decode_image, get_face_engine

FIX = Path(__file__).resolve().parents[1] / "data" / "fixtures"
pytestmark = pytest.mark.skipif(not (FIX / "real_webcam_1.jpg").exists(), reason="face fixtures are kept out of the repo")


def _score(name: str) -> float:
    img = decode_image((FIX / name).read_bytes())
    faces = get_face_engine().analyze(img)
    assert faces, name
    return get_antispoof().score(img, faces[0].bbox).real


@pytest.mark.parametrize("name", ["replay_phone_1.jpg", "replay_phone_2.jpg"])
def test_phone_replay_is_spoof(name):
    assert _score(name) < default_policy().spoof_hard_floor


def test_live_face_is_real():
    assert _score("real_webcam_1.jpg") > default_policy().spoof_threshold


def _cvpr(name: str) -> float:
    img = decode_image((FIX / name).read_bytes())
    faces = get_face_engine().analyze(img)
    assert faces, name
    r = get_antispoof().score(img, faces[0].bbox)
    assert r.cvpr is not None
    return r.cvpr


@pytest.mark.parametrize("name", ["replay_phone_close_1.jpg", "replay_phone_close_2.jpg"])
def test_phone_replay_without_bezel_minifasnet_is_fooled(name):
    # documents the known MiniFASNet weakness; the CVPR gate below is what catches it
    assert _score(name) > default_policy().spoof_hard_floor


@pytest.mark.parametrize("name", ["replay_phone_close_1.jpg", "replay_phone_close_2.jpg",
                                  "replay_phone_1.jpg", "replay_phone_2.jpg"])
def test_cvpr_gate_rejects_phone_replay(name):
    """Each replay frame fails the gate on its own. Measured 2026-09-20 at DET_SIZE=320: 0.0000 for three of
    them and 0.0504 for replay_phone_close_2 (0.0148 at 640; the box shifts a little with the detector size and
    the score follows the crop), so the bar is the mean threshold a session must clear, not the hard floor."""
    assert _cvpr(name) < default_policy().cvpr_threshold


def test_cvpr_gate_accepts_live_face():
    assert _cvpr("real_webcam_1.jpg") > default_policy().cvpr_threshold


@pytest.mark.parametrize("name", ["real_phone_video_1.jpg", "real_phone_video_2.jpg"])
def test_cvpr_gate_keeps_hard_genuine_phone_frames_above_floor(name):
    # frames from a genuine iPhone selfie video that scored ~0.02 at crop margin 0.2 (false reject)
    assert _cvpr(name) > default_policy().cvpr_hard_floor
