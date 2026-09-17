"""Download model weights needed by the server.

- InsightFace buffalo_l (detector + ArcFace r50)  -> ~/.insightface/models/buffalo_l
- MiniFASNet anti-spoof .pth (official minivision) -> weights/*.pth (then run convert.py)

Usage: uv run python weights/download.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
BASE = "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master/resources/anti_spoof_models/"
PTH = {
    "2.7_80x80_MiniFASNetV2.pth": "a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0",
    "4_0_0_80x80_MiniFASNetV1SE.pth": "84ee1d37d96894d5e82de5a57df044ef80a58be2b218b5ed7cdfd875ec2f5990",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, expected: str | None) -> Path:
    dst = HERE / name
    if not dst.exists():
        print(f"downloading {name} ...")
        r = requests.get(BASE + name, timeout=120)
        r.raise_for_status()
        dst.write_bytes(r.content)
    digest = sha256(dst)
    if expected and digest != expected:
        dst.unlink()
        sys.exit(f"sha256 mismatch for {name}: {digest}")
    print(f"ok {name} sha256={digest}")
    return dst


def download_buffalo_l() -> None:
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    print("ok buffalo_l:", sorted(app.models))


if __name__ == "__main__":
    for n, h in PTH.items():
        fetch(n, h)
    download_buffalo_l()
    print("next: uv run --with torch --with onnx python weights/convert.py")
