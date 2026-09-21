"""Video chunks decode into the same frames a JPEG client would have streamed: WebM (VP8) and MP4 as
MediaRecorder cuts them, raw H.264 access units as the phone plugins send them."""
import cv2
import numpy as np
import pytest

from app.services.face import decode_image
from app.services.video import VideoChunk, decode_chunks
from tests.video_util import access_units, encode_container


def _frames(n: int, w: int = 320, h: int = 240) -> list[np.ndarray]:
    """n frames whose brightness ramps, so decoded frames can be told apart and put in order."""
    out = []
    for i in range(n):
        img = np.full((h, w, 3), min(40 + i * 8, 250), dtype=np.uint8)
        cv2.circle(img, (w // 2, h // 2), 20 + i * 3, (255, 255, 255), -1)
        out.append(img)
    return out


def _brightness(jpeg: bytes) -> float:
    return float(decode_image(jpeg)[5:15, 5:15].mean())


def _split(blob: bytes, n: int) -> list[bytes]:
    size = len(blob) // n + 1
    return [blob[i:i + size] for i in range(0, len(blob), size)]


@pytest.mark.parametrize("fmt,codec", [("webm", "libvpx"), ("mp4", "libx264")])
def test_container_chunks_decode_in_order_with_device_time(fmt, codec):
    src = _frames(12)
    blob = encode_container(src, fmt, codec, fps=10)
    parts = _split(blob, 4)
    chunks = [VideoChunk(recv_ms=1000 + i * 300, client_ms=500 + i * 300, data=p) for i, p in enumerate(parts)]
    frames = decode_chunks(fmt, chunks, max_frames=900)
    assert len(frames) == 12
    bright = [_brightness(f.data) for f in frames]
    assert bright == sorted(bright), "frames come out in time order"
    assert bright[-1] - bright[0] > 60
    assert frames[0].client_ms == 500 and frames[-1].client_ms == pytest.approx(500 + 1100, abs=20)
    assert frames[0].recv_ms == 1000 and frames[-1].recv_ms >= 1300, "arrival follows the chunk the frame's time falls in"


def test_h264_access_units_keep_each_chunks_clocks():
    src = _frames(12)
    units = access_units(src)
    chunks = [VideoChunk(recv_ms=2000 + i * 66, client_ms=100 + i * 66, data=u) for i, u in enumerate(units)]
    frames = decode_chunks("h264", chunks, max_frames=900)
    assert len(frames) == 12
    bright = [_brightness(f.data) for f in frames]
    assert bright == sorted(bright)
    assert [f.client_ms for f in frames] == [100 + i * 66 for i in range(12)]
    assert [f.recv_ms for f in frames] == [2000 + i * 66 for i in range(12)]


def test_thinning_and_garbage():
    src = _frames(30)
    units = access_units(src)
    chunks = [VideoChunk(recv_ms=i * 33, client_ms=i * 33, data=u) for i, u in enumerate(units)]
    frames = decode_chunks("h264", chunks, max_frames=10)
    assert len(frames) == 10 and frames[0].client_ms == 0 and frames[-1].client_ms == 29 * 33
    assert decode_chunks("webm", [VideoChunk(0, 0, b"not a video")], 900) == []
    assert decode_chunks("jpeg", chunks, 900) == []
