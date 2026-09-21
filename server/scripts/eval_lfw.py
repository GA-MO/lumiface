"""Score the ArcFace matcher on LFW pairs and print ROC, EER, 10-fold accuracy and FAR/FRR per threshold.

Downloads LFW (funneled, 233 MB) and the 6000-pair protocol into data/lfw/ on first run,
embeds every image once with the same engine the server uses (buffalo_l; the face nearest the
image centre, as LFW labels it; 2x upscale when nothing is detected at 250 px),
caches the embeddings, then reports:

  genuine / impostor cosine distributions
  EER and its threshold, TAR at FAR 1%, 0.1%, 0.01%
  LFW 10-fold accuracy (threshold picked on the other 9 folds)
  FAR / FRR at the policy thresholds (0.40 relaxed, 0.45 balanced, 0.55 strict) and any --at values

Usage: uv run python scripts/eval_lfw.py [--root data/lfw] [--at 0.5 0.6] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import tarfile
import urllib.request
from pathlib import Path

import certifi
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.face import decode_image, get_face_engine  # noqa: E402

FILES = {
    "lfw-funneled.tgz": "https://ndownloader.figshare.com/files/5976015",
    "pairs.txt": "https://ndownloader.figshare.com/files/5976006",
}
POLICY_THRESHOLDS = {"relaxed": 0.40, "balanced": 0.45, "strict": 0.55}


def fetch(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dst = root / name
        if dst.exists():
            continue
        print(f"downloading {name} ...", flush=True)
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, context=ctx) as r, open(dst, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    images = root / "lfw_funneled"
    if not images.exists():
        print("extracting ...", flush=True)
        with tarfile.open(root / "lfw-funneled.tgz") as tf:
            tf.extractall(root)
    return images, root / "pairs.txt"


def read_pairs(path: Path) -> list[tuple[str, str, bool, int]]:
    lines = path.read_text().strip().splitlines()
    folds, per_fold = (int(x) for x in lines[0].split())
    pairs = []
    for i, line in enumerate(lines[1:]):
        parts = line.split()
        fold = i // (2 * per_fold)
        if len(parts) == 3:
            a, n1, n2 = parts
            pairs.append((f"{a}/{a}_{int(n1):04d}.jpg", f"{a}/{a}_{int(n2):04d}.jpg", True, fold))
        else:
            a, n1, b, n2 = parts
            pairs.append((f"{a}/{a}_{int(n1):04d}.jpg", f"{b}/{b}_{int(n2):04d}.jpg", False, fold))
    assert len(pairs) == folds * 2 * per_fold, (len(pairs), folds, per_fold)
    return pairs


def embed_all(images: Path, names: list[str], cache: Path) -> dict[str, np.ndarray | None]:
    done: dict[str, np.ndarray | None] = {}
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        done = {k: (None if v.size == 0 else v) for k, v in zip(z["names"], z["embs"])}
    todo = [n for n in names if n not in done]
    if todo:
        engine = get_face_engine()
        for i, n in enumerate(todo, 1):
            img = decode_image((images / n).read_bytes())
            faces = engine.analyze(img)
            if not faces:
                faces = engine.analyze(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
            done[n] = center_face(faces, img.shape[1], img.shape[0])
            if i % 500 == 0 or i == len(todo):
                print(f"  embedded {i}/{len(todo)}", flush=True)
        keys = list(done)
        np.savez(cache, names=np.array(keys), embs=np.array([done[k] if done[k] is not None else np.zeros(0, np.float32) for k in keys], dtype=object))
    return done


def center_face(faces, w: int, h: int) -> np.ndarray | None:
    """LFW labels the person nearest the image centre, not the largest face."""
    if not faces:
        return None
    cx, cy = w / 2, h / 2
    f = min(faces, key=lambda f: ((f.bbox[0] + f.bbox[2]) / 2 % w - cx) ** 2 + ((f.bbox[1] + f.bbox[3]) / 2 % h - cy) ** 2)
    return f.embedding


def far_frr(gen: np.ndarray, imp: np.ndarray, t: float) -> tuple[float, float]:
    return float((imp >= t).mean()), float((gen < t).mean())


def eer(gen: np.ndarray, imp: np.ndarray) -> tuple[float, float]:
    ts = np.linspace(-0.2, 1.0, 2401)
    best = min(ts, key=lambda t: abs(far_frr(gen, imp, t)[0] - far_frr(gen, imp, t)[1]))
    far, frr = far_frr(gen, imp, best)
    return float(best), (far + frr) / 2


def tar_at_far(gen: np.ndarray, imp: np.ndarray, far: float) -> tuple[float, float]:
    t = float(np.quantile(imp, 1 - far)) if far * len(imp) >= 1 else float(imp.max()) + 1e-6
    return t, float((gen >= t).mean())


def ten_fold(scores: np.ndarray, same: np.ndarray, folds: np.ndarray) -> tuple[float, float, list[float]]:
    ts = np.linspace(0.0, 1.0, 1001)
    accs, thresholds = [], []
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        if not tr.any():
            continue
        t = max(ts, key=lambda t: ((scores[tr] >= t) == same[tr]).mean())
        thresholds.append(t)
        accs.append(((scores[te] >= t) == same[te]).mean())
    return float(np.mean(accs)), float(np.std(accs)), thresholds


def pct(xs: np.ndarray) -> str:
    return " ".join(f"p{p}={np.percentile(xs, p):.3f}" for p in (0, 1, 5, 50, 95, 99, 100))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "lfw")
    ap.add_argument("--at", type=float, nargs="*", default=[])
    ap.add_argument("--limit", type=int, default=0, help="only the first N pairs (smoke test)")
    args = ap.parse_args()

    images, pairs_file = fetch(args.root)
    pairs = read_pairs(pairs_file)
    if args.limit:
        half = len(pairs) // 20
        pairs = pairs[: args.limit // 2] + pairs[half : half + args.limit // 2]
    names = sorted({n for a, b, _, _ in pairs for n in (a, b)})
    print(f"pairs={len(pairs)} images={len(names)}", flush=True)
    embs = embed_all(images, names, args.root / "embeddings.npz")

    scores, same, folds, skipped = [], [], [], 0
    for a, b, s, f in pairs:
        ea, eb = embs[a], embs[b]
        if ea is None or eb is None:
            skipped += 1
            scores.append(-1.0)
        else:
            scores.append(float(np.dot(ea, eb)))
        same.append(s)
        folds.append(f)
    scores, same, folds = np.array(scores), np.array(same), np.array(folds)
    gen, imp = scores[same], scores[~same]
    no_face = sum(1 for v in embs.values() if v is None)

    print(f"\nno face detected in {no_face}/{len(names)} images -> {skipped} pairs scored as -1 (counted as reject)")
    print("genuine  cosine:", pct(gen))
    print("impostor cosine:", pct(imp))
    t_eer, e = eer(gen, imp)
    print(f"\nEER {e * 100:.2f}% at threshold {t_eer:.3f}")
    for far in (1e-2, 1e-3, 1e-4):
        t, tar = tar_at_far(gen, imp, far)
        print(f"TAR {tar * 100:6.2f}% at FAR {far:g} (threshold {t:.3f})")
    acc, sd, ths = ten_fold(scores, same, folds)
    print(f"LFW 10-fold accuracy {acc * 100:.2f}% ± {sd * 100:.2f} (fold thresholds {min(ths):.2f}-{max(ths):.2f})")

    print("\nthreshold  FAR      FRR      preset")
    rows = sorted({**POLICY_THRESHOLDS, **{f"--at {t}": t for t in args.at}}.items(), key=lambda kv: kv[1])
    out = {}
    for label, t in rows:
        far, frr = far_frr(gen, imp, t)
        out[label] = {"threshold": t, "far": far, "frr": frr}
        print(f"{t:8.2f}   {far * 100:6.2f}%  {frr * 100:6.2f}%  {label}")
    summary = {"pairs": int(len(pairs)), "no_face_images": no_face, "eer": e, "eer_threshold": t_eer,
               "accuracy_10fold": acc, "genuine_p1": float(np.percentile(gen, 1)),
               "impostor_p99": float(np.percentile(imp, 99)), "impostor_max": float(imp.max()),
               "thresholds": out}
    (args.root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {args.root / 'summary.json'}")


if __name__ == "__main__":
    main()
