"""Server-side re-check of the smile challenge from InsightFace's 68 landmarks.

The client decides when the user smiled (ML Kit probability); a rigid latex or
silicone mask passes both passive gates, so the server confirms on the uploaded
frame that the mouth actually changed relative to the neutral frame.

Measured on 2026-09-17 samples (mouth width / inter-ocular, corner lift / inter-ocular):
genuine smile vs its neutral frame: width gain 1.14-1.16, lift +0.068..+0.071;
neutral vs neutral of the same session: gain 0.93-1.05, lift -0.04..+0.03.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..policy import get_policy

# iBUG 68-point indices
_L_EYE_OUTER, _R_EYE_OUTER = 36, 45
_MOUTH_L, _MOUTH_R = 48, 54
_LIP_TOP, _LIP_BOTTOM = 51, 57


@dataclass
class MouthMetrics:
    width: float  # mouth corner distance / inter-ocular distance
    lift: float   # how far the corners sit above the lip centre / inter-ocular (smile pulls them up)


def mouth_metrics(landmarks: np.ndarray | None) -> MouthMetrics | None:
    if landmarks is None or len(landmarks) < 68:
        return None
    pts = np.asarray(landmarks, dtype=np.float32)[:, :2]
    inter_ocular = float(np.linalg.norm(pts[_L_EYE_OUTER] - pts[_R_EYE_OUTER]))
    if inter_ocular < 1e-3:
        return None
    corners = (pts[_MOUTH_L] + pts[_MOUTH_R]) / 2
    centre = (pts[_LIP_TOP] + pts[_LIP_BOTTOM]) / 2
    width = float(np.linalg.norm(pts[_MOUTH_L] - pts[_MOUTH_R])) / inter_ocular
    lift = float(centre[1] - corners[1]) / inter_ocular
    return MouthMetrics(width=width, lift=lift)


def smile_ok(neutral: MouthMetrics | None, smiling: MouthMetrics | None) -> tuple[bool, dict]:
    """True when the smile frame's mouth widened or its corners lifted enough vs the neutral frame."""
    s = get_policy()
    if neutral is None or smiling is None:
        return True, {"skipped": "no landmarks"}
    gain = smiling.width / neutral.width if neutral.width > 1e-3 else 0.0
    lift = smiling.lift - neutral.lift
    ok = gain >= s.smile_min_width_gain or lift >= s.smile_min_lift
    return ok, {"width_gain": round(gain, 3), "lift": round(lift, 3)}
