"""Screen-flash liveness: the app fills the screen with a random colour sequence and
uploads one frame per colour; the light reflected by a real face must follow the
sequence. A screen replaying a video emits its own light and barely reflects ours,
and a pre-recorded video cannot know the colours picked seconds earlier."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from itertools import permutations

import numpy as np

from ..policy import get_policy

# Saturated primaries/secondaries: maximal chroma difference, zero-mean after centring.
PALETTE = {"FF0000": (1, 0, 0), "00FF00": (0, 1, 0), "0000FF": (0, 0, 1),
           "00FFFF": (0, 1, 1), "FF00FF": (1, 0, 1), "FFFF00": (1, 1, 0)}


def new_flash_colors() -> list[str]:
    n = min(get_policy().flash_count, len(PALETTE))
    keys = list(PALETTE)
    picked: list[str] = []
    while len(picked) < n:
        c = secrets.choice(keys)
        if c not in picked:
            picked.append(c)
    return picked


@dataclass
class FlashResult:
    correlation: float      # cosine between observed chroma deltas and the commanded sequence (-1..1)
    response: float         # RMS of observed deltas in 8-bit units; ~0 when nothing reflects
    order_ok: bool          # commanded order beats every other permutation of the same colours
    background_ratio: float | None = None  # surroundings' response / face response (see below)
    per_frame: list[list[float]] = field(default_factory=list)


def surroundings_mean_rgb(img_bgr: np.ndarray, bbox, inner: float = 1.3, outer: float = 2.2) -> np.ndarray:
    """Mean RGB of the ring around the face box (between `inner` and `outer` times its size).

    A real face sits closer to the phone than the wall behind it, so the ring reflects
    about half as much of the flash (Galaxy S25+: ratio 0.47-0.52 over 9 sessions). A glossy
    phone screen replaying a video reflects uniformly over its whole surface (ratio 1.2-2.3)."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    height, width = img_bgr.shape[:2]

    def box(k: float) -> tuple[int, int, int, int]:
        return (max(0, int(cx - k * w / 2)), max(0, int(cy - k * h / 2)),
                min(width, int(cx + k * w / 2)), min(height, int(cy + k * h / 2)))

    ox1, oy1, ox2, oy2 = box(outer)
    ix1, iy1, ix2, iy2 = box(inner)
    mask = np.zeros((height, width), dtype=bool)
    mask[oy1:oy2, ox1:ox2] = True
    mask[iy1:iy2, ix1:ix2] = False
    px = img_bgr[mask].astype(np.float32)
    if len(px) == 0:
        return np.zeros(3, dtype=np.float32)
    return px.mean(axis=0)[::-1]


def face_patch_mean_rgb(img_bgr: np.ndarray, bbox) -> np.ndarray:
    """Mean RGB of the cheeks/nose block (centre 50% x, 35..75% y of the face box)."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    w, h = x2 - x1, y2 - y1
    px1, px2 = int(x1 + 0.25 * w), int(x1 + 0.75 * w)
    py1, py2 = int(y1 + 0.35 * h), int(y1 + 0.75 * h)
    height, width = img_bgr.shape[:2]
    px1, px2 = max(0, px1), min(width, max(px1 + 1, px2))
    py1, py2 = max(0, py1), min(height, max(py1 + 1, py2))
    patch = img_bgr[py1:py2, px1:px2].astype(np.float32)
    return patch.reshape(-1, 3).mean(axis=0)[::-1]


def _chroma(v: np.ndarray) -> np.ndarray:
    """Remove the per-channel mean over frames (static skin/ambient colour) and the
    per-frame grey component (exposure drift), leaving only how the hue moved."""
    c = v - v.mean(axis=0, keepdims=True)
    return c - c.mean(axis=1, keepdims=True)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float(np.dot(a.ravel(), b.ravel()) / (na * nb))


def score_flash(observed_rgb: list[np.ndarray], colors: list[str],
                surroundings_rgb: list[np.ndarray] | None = None) -> FlashResult:
    """observed_rgb[i] is the face-patch mean RGB of the frame taken under colors[i];
    surroundings_rgb[i] (optional) the ring around the face in the same frame."""
    obs = _chroma(np.asarray(observed_rgb, dtype=np.float32))
    cmd = _chroma(np.asarray([PALETTE[c] for c in colors], dtype=np.float32))
    corr = _cos(obs, cmd)
    response = float(np.sqrt((obs ** 2).mean()))
    order_ok = True
    for perm in permutations(range(len(colors))):
        if list(perm) == list(range(len(colors))):
            continue
        if _cos(obs, cmd[list(perm)]) >= corr:
            order_ok = False
            break
    ratio = None
    if surroundings_rgb is not None:
        bg = _chroma(np.asarray(surroundings_rgb, dtype=np.float32))
        ratio = float(np.sqrt((bg ** 2).mean()) / max(response, 1e-3))
    return FlashResult(correlation=corr, response=response, order_ok=order_ok, background_ratio=ratio,
                       per_frame=[[round(float(x), 2) for x in row] for row in obs])


def flash_passes(r: FlashResult) -> bool:
    s = get_policy()
    if r.background_ratio is not None and r.background_ratio > s.flash_max_background_ratio:
        return False
    return r.correlation >= s.flash_min_correlation and r.response >= s.flash_min_response and r.order_ok
