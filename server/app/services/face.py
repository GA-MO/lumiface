"""Face detection, pose and ArcFace embeddings via InsightFace buffalo_l (CPU)."""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from ..config import get_settings
from .inference import session_options


@dataclass
class FaceResult:
    bbox: np.ndarray  # x1, y1, x2, y2 (float)
    det_score: float
    pitch: float
    yaw: float
    roll: float
    embedding: np.ndarray  # L2-normalised, 512-d float32
    landmarks: np.ndarray | None = None  # 68 x 3 (iBUG order) when the landmark model ran

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])

    @property
    def area(self) -> float:
        return self.width * self.height


class BadImage(ValueError):
    """Undecodable or oversized upload; callers answer BAD_IMAGE instead of 500."""


def decode_image(data: bytes) -> np.ndarray:
    """JPEG/PNG bytes -> BGR uint8 array, honouring EXIF orientation (phone photos)."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > get_settings().max_image_pixels:
            raise BadImage("image too large")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except BadImage:
        raise
    except Exception as e:  # PIL raises a zoo of types for corrupt data
        raise BadImage(str(e)) from e
    return np.ascontiguousarray(np.asarray(img)[:, :, ::-1])


class FaceEngine:
    def __init__(self) -> None:
        from insightface.app import FaceAnalysis

        s = get_settings()
        self.app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition", "landmark_3d_68"],
            sess_options=session_options(),
        )
        self.app.prepare(ctx_id=0, det_size=(s.det_size, s.det_size))

    def analyze(self, img_bgr: np.ndarray) -> list[FaceResult]:
        out = []
        for f in self.app.get(img_bgr):
            pitch, yaw, roll = (float(v) for v in f.pose)
            out.append(
                FaceResult(
                    bbox=np.asarray(f.bbox, dtype=np.float32),
                    det_score=float(f.det_score),
                    pitch=pitch,
                    yaw=yaw,
                    roll=roll,
                    embedding=np.asarray(f.normed_embedding, dtype=np.float32),
                    landmarks=None if getattr(f, "landmark_3d_68", None) is None
                    else np.asarray(f.landmark_3d_68, dtype=np.float32),
                )
            )
        out.sort(key=lambda r: r.area, reverse=True)
        return out


_engine: FaceEngine | None = None
_engine_lock = threading.Lock()


def get_face_engine() -> FaceEngine:
    """The one engine, built on first use; the lock keeps a request that lands during the startup warm-up from building a second."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = FaceEngine()
    return _engine


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
