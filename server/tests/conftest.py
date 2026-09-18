import os
import tempfile
from pathlib import Path

os.environ.update({
    "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/test.db",
    "BOOTSTRAP_API_KEY": "test-key",
    "ADMIN_API_KEY": "admin-key",
    "MIN_FACE_SIZE": "60",
    "ENROLL_MAX_PITCH": "35",
    "CHALLENGE_POOL": "smile",
    "SMILE_ENFORCE": "0",  # API tests stream the same still for every frame; see test_smile_enforced_rejects_static_face
    "FLASH_ENFORCE": "0",  # same reason; see test_flash_enforced_rejects_unlit_frames
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


def run_stream(client, session, jpeg, *, per_window=2, token=None, sleep=0.13, order=None, pause=0.0):
    """Drive a session's WebSocket the way a device does: hello, frames, events, end.

    Every frame gets a distinct tail so it hashes differently (a real camera never repeats bytes);
    device stamps run 200 ms per frame with each event raised 150 ms before the frame that follows it;
    `order` overrides the event sequence; `pause` sleeps before the end so server-clock tests can
    make the session take real time. Returns (plan, last message).
    """
    import time

    sid, tok = session["session_id"], token if token is not None else session["session_token"]
    seq = 0
    with client.websocket_connect(f"/v1/sessions/{sid}/stream") as ws:
        ws.send_json({"type": "hello", "token": tok, "client": {"platform": "test"}})
        plan = ws.receive_json()
        if plan.get("type") != "plan":
            return plan, None

        def frames(n=per_window):
            nonlocal seq
            for _ in range(n):
                ws.send_bytes((seq * 200).to_bytes(8, "big") + jpeg + seq.to_bytes(4, "big"))
                seq += 1

        def event(name, index=None):
            ws.send_json({"type": "event", "name": name, **({"index": index} if index is not None else {}),
                          "ts": seq * 200 - 150})

        if order is None:
            frames()
            event("aligned")
            for i in range(len(plan["challenges"])):
                frames()
                event("challenge_done", i)
            for i in range(len(plan["flash_colors"])):
                event("flash", i)
                time.sleep(sleep)  # past FLASH_LATENCY_MS, so these frames land inside the colour's window
                frames()
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
        ws.send_json({"type": "end"})
        return plan, ws.receive_json()
