import os
import tempfile
from pathlib import Path

os.environ.update({
    "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/test.db",
    "BOOTSTRAP_API_KEY": "test-key",
    "MIN_FACE_SIZE": "60",
    "ENROLL_MAX_PITCH": "35",
    "CHALLENGE_POOL": "blink,smile",
    "SMILE_ENFORCE": "0",  # API tests upload the same still for every frame; see test_smile_enforced_rejects_static_face
    "FLASH_ENFORCE": "0",  # same reason; see test_flash_enforced_rejects_unlit_frames
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


def make_meta(challenges, start=0, step=800, challenge_ms=400, flash_colors=()):
    kinds = ["neutral_start", *[f"challenge_{i}" for i in range(len(challenges))],
             *[f"flash_{i}" for i in range(len(flash_colors))], "neutral_end"]
    return {
        "frames": [{"kind": k, "ts_ms": start + i * step} for i, k in enumerate(kinds)],
        "challenge_durations_ms": [challenge_ms] * len(challenges),
        "client": {"platform": "test"},
    }
