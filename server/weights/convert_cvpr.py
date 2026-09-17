"""Download the CVPR-2024 FAS ResNet50 weights and export them to ONNX for the server.

Usage: uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py [--force]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "cvpr2024"
PTH = OUT_DIR / "full_resnet50.pth"
ONNX = OUT_DIR / "resnet50.onnx"
DRIVE_ID = "1VpWN8CXdVVLTwyTPABeFXmr3UnnenjYe"
PTH_SHA256 = "9d1a67810978f19564b0a6147f6d879bf6f2808a92d408a65f1aaf272422206d"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    force = "--force" in sys.argv
    OUT_DIR.mkdir(exist_ok=True)
    if not PTH.exists():
        import gdown

        print("downloading full_resnet50.pth (283 MB) ...")
        gdown.download(id=DRIVE_ID, output=str(PTH), quiet=False)
    digest = sha256(PTH)
    print("full_resnet50.pth sha256 =", digest)
    if PTH_SHA256 != "9d1a67810978f19564b0a6147f6d879bf6f2808a92d408a65f1aaf272422206d" and digest != PTH_SHA256:
        sys.exit("sha256 mismatch - refusing to convert")
    if ONNX.exists() and not force:
        print("resnet50.onnx exists, pass --force to re-export")
        return

    import torch

    sys.path.insert(0, str(HERE))
    from cvpr_resnet_arch import resnet50  # noqa: E402

    model = resnet50(num_classes=2)
    sd = torch.load(PTH, map_location="cpu")
    if "state_dict_ema" in sd and sd["state_dict_ema"] is not None:
        sd = sd["state_dict_ema"]
        sd.pop("n_averaged", None)
    elif "state_dict" in sd:
        sd = sd["state_dict"]
    sd = {k.removeprefix("module.").removeprefix("module."): v for k, v in sd.items()}
    print(model.load_state_dict(sd, strict=True))

    class Wrapped(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            out = self.m(x)
            if isinstance(out, (tuple, list)):
                out = [t for t in out if t.shape[-1] == 2][0]
            return torch.softmax(out, dim=-1)

    w = Wrapped(model).eval()
    torch.onnx.export(w, torch.zeros(1, 3, 224, 224), str(ONNX), input_names=["input"], output_names=["output"],
                      opset_version=11, dynamo=False)
    print("wrote", ONNX, ONNX.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
