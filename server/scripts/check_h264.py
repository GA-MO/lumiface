"""Decodes the access units a device test wrote (`h264_test.bin`: 8-byte big-endian ms + 4-byte length + unit,
repeated) with the server's decoder and prints what came out: frame count, size, timestamps and where the
white disc sits in the first, middle and last frame, so orientation and mirroring can be read off.

    adb shell "run-as ai.lumiface.lumiface.test cat files/h264_test.bin" > h264_test.bin
    xcrun devicectl device copy from --device <udid> --domain-type appDataContainer \\
        --domain-identifier com.example.faceCheckinExample --source Documents/h264_test.bin --destination h264_test.bin
    uv run python scripts/check_h264.py h264_test.bin
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.face import decode_image  # noqa: E402
from app.services.video import VideoChunk, decode_chunks  # noqa: E402


def main(path: str) -> None:
    raw = Path(path).read_bytes()
    chunks, i = [], 0
    while i < len(raw):
        ts, n = struct.unpack(">qi", raw[i:i + 12])
        i += 12
        chunks.append(VideoChunk(recv_ms=ts, client_ms=ts, data=raw[i:i + n]))
        i += n
    frames = decode_chunks("h264", chunks, 900)
    print(f"{len(chunks)} units, {len(frames)} frames, ts {chunks[0].client_ms}..{chunks[-1].client_ms}")
    if not frames:
        return
    print("size (h, w):", decode_image(frames[0].data).shape[:2])
    for k in (0, len(frames) // 2, len(frames) - 1):
        img = decode_image(frames[k].data)
        ys, xs = np.where(img[:, :, 0] > 180)
        centre = (int(xs.mean()), int(ys.mean())) if len(xs) else None
        print(f"frame {k} at {frames[k].client_ms} ms: disc centre (x, y) = {centre}")


if __name__ == "__main__":
    main(sys.argv[1])
