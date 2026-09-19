"""Video chunks from the device become the frames the pipeline judges.

The SDKs stream video the way a camera app records it, one chunk per WebSocket message with the
device time of the chunk's first frame in front: `webm` (VP8, MediaRecorder on the web), `mp4`
(H.264, MediaRecorder on Safari) or `h264` (one Annex-B access unit per message, the phone
plugins). Every chunk is decoded here into JPEG frames with both clocks, so everything after this
point, the windows, the stored session, the replay set, sees exactly what a JPEG-streaming client
would have sent, just at the camera's frame rate.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import av
import cv2
import numpy as np

from .stream import StreamFrame

FORMATS = ("jpeg", "webm", "mp4", "h264")
CONTAINER_FORMATS = {"webm": "webm", "mp4": "mp4"}
JPEG_QUALITY = 90


@dataclass
class VideoChunk:
    recv_ms: int
    client_ms: int
    data: bytes


def _jpeg(frame: av.VideoFrame) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame.to_ndarray(format="bgr24"), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("jpeg encode failed")
    return buf.tobytes()


def _subsample(frames: list[StreamFrame], max_frames: int) -> list[StreamFrame]:
    if len(frames) <= max_frames:
        return frames
    idx = np.linspace(0, len(frames) - 1, max_frames).round().astype(int)
    return [frames[i] for i in dict.fromkeys(idx)]


def _decode_access_units(chunks: list[VideoChunk]) -> list[StreamFrame]:
    """`h264`: each chunk is one access unit stamped by the device, so its frame keeps both of the
    chunk's clocks. Baseline profile, no B-frames: the decoder hands frames back in order, at most
    one behind, which the flush at the end drains."""
    ctx = av.CodecContext.create("h264", "r")
    out: list[StreamFrame] = []
    pending: list[VideoChunk] = []
    for c in chunks:
        pending.append(c)
        for packet in ctx.parse(c.data):
            for frame in ctx.decode(packet):
                src = pending.pop(0) if pending else c
                out.append(StreamFrame(recv_ms=src.recv_ms, client_ms=src.client_ms, data=_jpeg(frame)))
    for packet in ctx.parse(b""):
        for frame in ctx.decode(packet):
            src = pending.pop(0) if pending else chunks[-1]
            out.append(StreamFrame(recv_ms=src.recv_ms, client_ms=src.client_ms, data=_jpeg(frame)))
    for frame in ctx.decode(None):
        src = pending.pop(0) if pending else chunks[-1]
        out.append(StreamFrame(recv_ms=src.recv_ms, client_ms=src.client_ms, data=_jpeg(frame)))
    return out


def _decode_container(fmt: str, chunks: list[VideoChunk]) -> list[StreamFrame]:
    """`webm` / `mp4`: MediaRecorder's chunks concatenate into one stream whose frame times start at
    the first chunk's device time; a frame's arrival time is that of the chunk its time falls in."""
    start = chunks[0].client_ms
    bounds = [c.client_ms for c in chunks]
    recv = [c.recv_ms for c in chunks]

    def recv_for(client_ms: int) -> int:
        i = int(np.searchsorted(bounds, client_ms, side="right")) - 1
        return recv[max(0, min(i, len(recv) - 1))]

    out: list[StreamFrame] = []
    with av.open(io.BytesIO(b"".join(c.data for c in chunks)), format=CONTAINER_FORMATS[fmt]) as container:
        stream = container.streams.video[0]
        for i, frame in enumerate(container.decode(stream)):
            t = frame.time if frame.time is not None else i / float(stream.average_rate or 30)
            client_ms = start + int(round(t * 1000))
            out.append(StreamFrame(recv_ms=recv_for(client_ms), client_ms=client_ms, data=_jpeg(frame)))
    return out


def decode_chunks(fmt: str, chunks: list[VideoChunk], max_frames: int) -> list[StreamFrame]:
    """The chunks of one session as JPEG frames in time order, at most `max_frames` of them (evenly
    thinned beyond that). An undecodable stream yields no frames, which the pipeline answers as
    `FRAME_COUNT`."""
    if not chunks or fmt not in FORMATS or fmt == "jpeg":
        return []
    try:
        frames = _decode_access_units(chunks) if fmt == "h264" else _decode_container(fmt, chunks)
    except (av.error.FFmpegError, ValueError, IndexError):
        return []
    frames.sort(key=lambda f: f.client_ms)
    return _subsample(frames, max_frames)
