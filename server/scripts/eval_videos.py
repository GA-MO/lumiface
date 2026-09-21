"""Run the passive anti-spoof gates over folders of videos and report pass rates.

Layout: <root>/<category>/*.mp4|jpg where a category name containing "selfie", "real" or
"live" is genuine and everything else is an attack. A few evenly spaced frames per
video (or the still itself) are scored exactly like uploaded check-in frames (MiniFASNet
ensemble + CVPR-2024 crop gate) and an item "passes" when its mean scores clear the
current .env thresholds.

Usage: uv run python scripts/eval_videos.py data/samples/axondata [frames_per_video]
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402
from app.services.antispoof import get_antispoof  # noqa: E402
from app.services.face import get_face_engine  # noqa: E402

GENUINE = ("selfie", "real", "live")


def frames(path: Path, n: int):
    if path.suffix.lower() in (".jpg", ".jpeg", ".png"):
        img = cv2.imread(str(path))
        if img is not None:
            yield img
        return
    cap = cv2.VideoCapture(str(path))
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for idx in np.linspace(0, max(count - 1, 0), n, dtype=int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, img = cap.read()
        if ok:
            yield img
    cap.release()


def score_video(path: Path, n: int) -> dict | None:
    s = get_settings()
    real, cvpr = [], []
    for img in frames(path, n):
        h, w = img.shape[:2]
        if max(h, w) > 1280:
            f = 1280 / max(h, w)
            img = cv2.resize(img, (int(w * f), int(h * f)))
        faces = get_face_engine().analyze(img)
        if not faces:
            continue
        sp = get_antispoof().score(img, faces[0].bbox)
        real.append(sp.real)
        if sp.cvpr is not None:
            cvpr.append(sp.cvpr)
    if not real:
        return None
    passes = float(np.mean(real)) >= s.spoof_threshold and min(real) >= s.spoof_hard_floor
    if cvpr:
        passes = passes and float(np.mean(cvpr)) >= s.cvpr_threshold and min(cvpr) >= s.cvpr_hard_floor
    return {"minifasnet": float(np.mean(real)), "cvpr": float(np.mean(cvpr)) if cvpr else None,
            "frames": len(real), "passes": passes}


def main(root: Path, n: int) -> None:
    for cat in sorted(p for p in root.iterdir() if p.is_dir()):
        genuine = any(g in cat.name.lower() for g in GENUINE)
        rows = []
        for v in sorted(p for p in cat.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".jpg", ".jpeg", ".png")):
            r = score_video(v, n)
            if r is None:
                print(f"  {v.name}: no face")
                continue
            rows.append(r)
            print(f"  {v.name}: minifasnet={r['minifasnet']:.3f} cvpr={r['cvpr'] if r['cvpr'] is None else round(r['cvpr'], 3)}"
                  f" frames={r['frames']} -> {'PASS' if r['passes'] else 'reject'}")
        if not rows:
            continue
        passed = sum(r["passes"] for r in rows)
        label = "genuine (want PASS)" if genuine else "attack (want reject)"
        print(f"{cat.name}: {label}: {passed}/{len(rows)} pass · "
              f"minifasnet median={np.median([r['minifasnet'] for r in rows]):.3f} · "
              f"cvpr median={np.median([r['cvpr'] for r in rows if r['cvpr'] is not None] or [float('nan')]):.3f}")
        print()


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
