"""Regression fixtures captured 2026-09-17 through the Android emulator + Mac webcam:
real_webcam_*  = live face; replay_phone_* = a video of the same person played on a phone screen."""
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.antispoof import get_antispoof
from app.services.face import decode_image, get_face_engine

FIX = Path(__file__).parent / "fixtures"


def _score(name: str) -> float:
    img = decode_image((FIX / name).read_bytes())
    faces = get_face_engine().analyze(img)
    assert faces, name
    return get_antispoof().score(img, faces[0].bbox).real


@pytest.mark.parametrize("name", ["replay_phone_1.jpg", "replay_phone_2.jpg"])
def test_phone_replay_is_spoof(name):
    assert _score(name) < get_settings().spoof_hard_floor


def test_live_face_is_real():
    assert _score("real_webcam_1.jpg") > get_settings().spoof_threshold


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
    assert _score(name) > get_settings().spoof_hard_floor


@pytest.mark.parametrize("name", ["replay_phone_close_1.jpg", "replay_phone_close_2.jpg",
                                  "replay_phone_1.jpg", "replay_phone_2.jpg"])
def test_cvpr_gate_rejects_phone_replay(name):
    assert _cvpr(name) < get_settings().cvpr_hard_floor


def test_cvpr_gate_accepts_live_face():
    assert _cvpr("real_webcam_1.jpg") > get_settings().cvpr_threshold


@pytest.mark.parametrize("name", ["real_phone_video_1.jpg", "real_phone_video_2.jpg"])
def test_cvpr_gate_keeps_hard_genuine_phone_frames_above_floor(name):
    # frames from a genuine iPhone selfie video that scored ~0.02 at crop margin 0.2 (false reject)
    assert _cvpr(name) > get_settings().cvpr_hard_floor
