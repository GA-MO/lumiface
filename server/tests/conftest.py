import os
import tempfile
from pathlib import Path

os.environ.update({
    "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/test.db",
    "BOOTSTRAP_API_KEY": "test-key",
    "ADMIN_API_KEY": "admin-key",
    "MIN_FACE_SIZE": "60",
    "REFERENCE_MAX_PITCH": "35",
    "OVAL_WIDTH_FRACTION": "0.35",  # the person crops carry a margin of one face width; see run_stream
    "FLASH_ENFORCE": "0",  # API tests stream the same still for every frame; see test_flash_enforced_rejects_unlit_frames
    "MIN_SESSION_MS": "0",  # the server clocks the stream itself; see test_too_fast_on_the_server_clock
    "MIN_CHALLENGE_MS": "0",
    "DEBUG": "1",
    "WEIGHTS_DIR": str(Path(__file__).resolve().parents[1] / "weights"),
})

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from insightface.data import get_image  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-API-Key": "test-key"}
ADMIN = {"X-Admin-Key": "admin-key"}


def _jpeg(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buf.tobytes()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def person_crops():
    """Two different people cut out of insightface's sample group photo (with margin)."""
    from app.services.face import get_face_engine

    img = get_image("t1")
    faces = get_face_engine().analyze(img)
    assert len(faces) >= 2
    crops = []
    for f in faces[:2]:
        x1, y1, x2, y2 = f.bbox
        w, h = x2 - x1, y2 - y1
        x1, y1 = max(0, int(x1 - w)), max(0, int(y1 - h))
        x2, y2 = min(img.shape[1], int(x2 + w)), min(img.shape[0], int(y2 + h))
        crops.append(_jpeg(img[y1:y2, x1:x2]))
    return crops


def blank_jpeg() -> bytes:
    """A grey frame with nobody in it."""
    return _jpeg(np.full((240, 320, 3), 128, np.uint8))


def far_frame(jpeg: bytes) -> bytes:
    """The same still seen from twice the distance: padded to twice its size, so the face box halves."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jpeg
    h, w = img.shape[:2]
    return _jpeg(cv2.copyMakeBorder(img, h // 2, h // 2, w // 2, w // 2, cv2.BORDER_REPLICATE))


def run_stream(client, session, jpeg, *, per_window=2, token=None, sleep=0.13, order=None, pause=0.0, move=True,
               fmt="jpeg", flash_jpeg=None):
    """Drive a session's WebSocket the way a device does: hello, frames, events, end.

    Every frame gets a distinct tail so it hashes differently (a real camera never repeats bytes);
    device stamps run 200 ms per frame with each event raised 150 ms before the frame that follows it;
    the face_move window opens with a padded, far copy of the still and closes with the still itself
    (`move=False` streams the still throughout, so the server sees no movement); `order` overrides the
    event sequence; `pause` sleeps before the end so server-clock tests can make the session take real
    time. `fmt="h264"` sends each frame as one encoded access unit the way the phone plugins do;
    `fmt="webm"` records the whole session as one VP8 stream and sends it in chunks the way
    MediaRecorder does. `flash_jpeg` streams another still during the flash windows only (a face swapped
    in for the flash). Returns (plan, last message).
    """
    import time

    from tests.video_util import access_units, encode_container

    sid, tok = session["session_id"], token if token is not None else session["session_token"]
    seq = 0
    far = far_frame(jpeg) if move else jpeg
    decoded = {}

    def image(data):
        # One size for the whole stream, with even sides: the far frame's, so its face stays detectable.
        if data not in decoded:
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            big = cv2.imdecode(np.frombuffer(far, np.uint8), cv2.IMREAD_COLOR)
            h, w = (big.shape[0] // 2) * 2, (big.shape[1] // 2) * 2
            decoded[data] = cv2.resize(img, (w, h)) if img.shape[:2] != (h, w) else img[:h, :w]
        return decoded[data]

    def uniform(img, i):
        # A camera never repeats bytes: a small marker wanders across the top rows frame by frame.
        img = img.copy()
        x = (i * 17) % max(img.shape[1] - 8, 1)
        img[0:8, x:x + 8] = (255, 255, 255)
        return img

    recorded = []
    with client.websocket_connect(f"/v1/sessions/{sid}/stream") as ws:
        ws.send_json({"type": "hello", "token": tok, "client": {"platform": "test"}, "format": fmt})
        plan = ws.receive_json()
        if plan.get("type") != "plan":
            return plan, None

        def frames(n=per_window, data=jpeg):
            nonlocal seq
            for _ in range(n):
                if fmt == "jpeg":
                    ws.send_bytes((seq * 200).to_bytes(8, "big") + data + seq.to_bytes(4, "big"))
                elif fmt == "h264":
                    recorded.append(uniform(image(data), seq))
                    ws.send_bytes((seq * 200).to_bytes(8, "big") + access_units([recorded[-1]], fps=5)[0])
                else:
                    recorded.append(uniform(image(data), seq))
                seq += 1

        def event(name, index=None):
            ws.send_json({"type": "event", "name": name, **({"index": index} if index is not None else {}),
                          "ts": seq * 200 - 150})

        if order is None:
            frames()
            event("aligned")
            for i in range(len(plan["challenges"])):
                frames(data=far)
                frames()
                event("challenge_done", i)
            for i in range(len(plan["flash_colors"])):
                event("flash", i)
                time.sleep(sleep)  # past FLASH_LATENCY_MS, so these frames land inside the colour's window
                frames(data=flash_jpeg or jpeg)
            if plan["flash_colors"]:
                event("flash_end")
            frames()
        else:
            for step in order:
                frames(1)
                if step != "frames":
                    name, _, idx = step.partition(":")
                    event(name, int(idx) if idx else None)
        if pause:
            time.sleep(pause)
        if fmt == "webm":
            blob = encode_container(recorded, "webm", "libvpx", fps=5)
            size = len(blob) // 4 + 1
            for i in range(0, len(blob), size):
                ws.send_bytes((i // size * 800).to_bytes(8, "big") + blob[i:i + size])
        ws.send_json({"type": "end"})
        return plan, ws.receive_json()
