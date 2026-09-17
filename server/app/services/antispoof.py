"""Passive anti-spoofing.

1. MiniFASNet ensemble (Silent-Face-Anti-Spoofing): 80x80 BGR crop at 2.7x / 4x the face box,
   raw 0-255 floats (upstream does NOT divide by 255). Classes [print, real, replay]; real = softmax[1].
   Strong on printed photos and on screens whose bezel is in the crop; fooled by a bezel-free screen.
2. CVPR-2024 FAS challenge ResNet50 (Xianhua-He, MIT), trained with moire augmentation: face box + 30 %
   margin (CVPR_CROP_MARGIN; the score is very sensitive to it), resized 224x224 RGB, ImageNet normalisation, softmax [live, spoof]; live = out[0].
   Only reliable on the face crop, not on the full frame (measured 2026-09-17).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from ..config import get_settings

MODELS = (("minifasnet_v2_2.7.onnx", 2.7), ("minifasnet_v1se_4.0.onnx", 4.0))


CVPR_MODEL = "cvpr2024/resnet50.onnx"
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


@dataclass
class SpoofResult:
    real: float                 # MiniFASNet ensemble real probability
    per_model: dict[str, float]
    cvpr: float | None = None   # CVPR-2024 ResNet50 live probability on the face crop (None if disabled)


def _scaled_box(src_w: int, src_h: int, bbox, scale: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x, y, bw, bh = x1, y1, x2 - x1 + 1, y2 - y1 + 1
    scale = min((src_h - 1) / bh, min((src_w - 1) / bw, scale))
    nw, nh = bw * scale, bh * scale
    cx, cy = bw / 2 + x, bh / 2 + y
    l, t, r, b = cx - nw / 2, cy - nh / 2, cx + nw / 2, cy + nh / 2
    if l < 0:
        r -= l
        l = 0
    if t < 0:
        b -= t
        t = 0
    if r > src_w - 1:
        l -= r - src_w + 1
        r = src_w - 1
    if b > src_h - 1:
        t -= b - src_h + 1
        b = src_h - 1
    return int(l), int(t), int(r), int(b)


def crop_face(img_bgr: np.ndarray, bbox, scale: float, size: int = 80) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    l, t, r, b = _scaled_box(w, h, [int(v) for v in bbox], scale)
    return cv2.resize(img_bgr[t : b + 1, l : r + 1], (size, size))


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max())
    return e / e.sum()


def face_crop_margin(img_bgr: np.ndarray, bbox, margin: float = 0.2) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    H, W = img_bgr.shape[:2]
    x1, y1 = max(0, int(x1 - w * margin)), max(0, int(y1 - h * margin))
    x2, y2 = min(W, int(x2 + w * margin)), min(H, int(y2 + h * margin))
    return img_bgr[y1:y2, x1:x2]


class AntiSpoof:
    def __init__(self) -> None:
        s = get_settings()
        wd = Path(s.weights_dir)
        self.sessions: list[tuple[str, float, ort.InferenceSession]] = []
        for name, scale in MODELS:
            path = wd / name
            if not path.exists():
                raise FileNotFoundError(f"{path} missing - run weights/download.py + weights/convert.py")
            self.sessions.append((name, scale, ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])))
        self.cvpr: ort.InferenceSession | None = None
        if s.cvpr_enabled:
            path = wd / CVPR_MODEL
            if not path.exists():
                raise FileNotFoundError(f"{path} missing - see weights/cvpr2024/README.md (or set CVPR_ENABLED=0)")
            self.cvpr = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    def score(self, img_bgr: np.ndarray, bbox) -> SpoofResult:
        per = {}
        for name, scale, sess in self.sessions:
            crop = crop_face(img_bgr, bbox, scale).astype(np.float32).transpose(2, 0, 1)[None]
            logits = sess.run(None, {"input": crop})[0][0]
            per[name] = float(_softmax(logits)[1])
        cvpr = None
        if self.cvpr is not None:
            face = cv2.resize(face_crop_margin(img_bgr, bbox, get_settings().cvpr_crop_margin), (224, 224))
            rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            inp = ((rgb - _MEAN) / _STD).transpose(2, 0, 1)[None]
            cvpr = float(self.cvpr.run(None, {"input": inp})[0][0][0])
        return SpoofResult(real=float(np.mean(list(per.values()))), per_model=per, cvpr=cvpr)


@lru_cache
def get_antispoof() -> AntiSpoof:
    return AntiSpoof()
