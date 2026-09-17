"""Print match / spoof score distributions from folders of photos to pick thresholds.

Layout:
  <root>/real/<employee_id>/*.jpg      genuine photos (several per person, incl. the enrolled one)
  <root>/spoof/*.jpg                   photos of printed pictures / phone screens (any person)

Usage: uv run python scripts/calibrate.py <root>
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.antispoof import get_antispoof  # noqa: E402
from app.services.face import cosine, decode_image, get_face_engine  # noqa: E402

EXT = {".jpg", ".jpeg", ".png", ".heic"}


def analyze(path: Path):
    img = decode_image(path.read_bytes())
    faces = get_face_engine().analyze(img)
    if not faces:
        return None
    f = faces[0]
    return f.embedding, get_antispoof().score(img, f.bbox).real


def pct(xs, ps=(0, 5, 50, 95, 100)):
    return " ".join(f"p{p}={np.percentile(xs, p):.3f}" for p in ps) if xs else "n/a"


def main(root: Path) -> None:
    people: dict[str, list[tuple[np.ndarray, float]]] = {}
    for d in sorted((root / "real").glob("*")):
        if d.is_dir():
            people[d.name] = [r for p in sorted(d.iterdir()) if p.suffix.lower() in EXT and (r := analyze(p))]
    spoof = [r[1] for p in sorted((root / "spoof").glob("*")) if p.suffix.lower() in EXT and (r := analyze(p))]

    same, diff = [], []
    for pid, items in people.items():
        for (a, _), (b, _) in itertools.combinations(items, 2):
            same.append(cosine(a, b))
    for (pa, ia), (pb, ib) in itertools.combinations(people.items(), 2):
        for (a, _), (b, _) in itertools.product(ia, ib):
            diff.append(cosine(a, b))
    real_spoof = [s for items in people.values() for _, s in items]

    print(f"people={len(people)} real_photos={len(real_spoof)} spoof_photos={len(spoof)}")
    print("match cosine  same person :", pct(same))
    print("match cosine  diff person :", pct(diff))
    print("  -> MATCH_THRESHOLD between max(diff) and min(same), e.g.",
          f"{(max(diff) + min(same)) / 2:.2f}" if same and diff else "n/a")
    print("spoof real-score  genuine :", pct(real_spoof))
    print("spoof real-score  attacks :", pct(spoof))
    print("  -> SPOOF_THRESHOLD between max(attacks) and min(genuine), e.g.",
          f"{(max(spoof) + min(real_spoof)) / 2:.2f}" if spoof and real_spoof else "n/a")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
