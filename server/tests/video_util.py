"""Encoders for tests: what MediaRecorder and the phone plugins produce, made from still frames."""
import io

import av
import numpy as np


def encode_container(frames: list[np.ndarray], fmt: str, codec: str, fps: int = 10) -> bytes:
    buf = io.BytesIO()
    with av.open(buf, "w", format=fmt) as container:
        stream = container.add_stream(codec, rate=fps)
        stream.width, stream.height = frames[0].shape[1], frames[0].shape[0]
        stream.pix_fmt = "yuv420p"
        if codec == "libx264":
            stream.options = {"profile": "baseline", "tune": "zerolatency", "movflags": "frag_keyframe+empty_moov"}
        for img in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buf.getvalue()


def access_units(frames: list[np.ndarray], fps: int = 10) -> list[bytes]:
    """Annex-B H.264, one access unit per frame, parameter sets in front of every keyframe (what the
    Android and iOS plugins send)."""
    ctx = av.CodecContext.create("libx264", "w")
    ctx.width, ctx.height, ctx.pix_fmt = frames[0].shape[1], frames[0].shape[0], "yuv420p"
    ctx.framerate = fps
    ctx.options = {"profile": "baseline", "tune": "zerolatency", "x264-params": "keyint=5:annexb=1:repeat-headers=1"}
    units = []
    for img in frames:
        for packet in ctx.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
            units.append(bytes(packet))
    for packet in ctx.encode():
        units.append(bytes(packet))
    return units


