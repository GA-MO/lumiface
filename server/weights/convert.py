"""Export the official MiniFASNet .pth weights to ONNX (opset 11, dynamic batch).

Usage: uv run --with torch --with onnx python weights/convert.py
Produces weights/minifasnet_v2_2.7.onnx and weights/minifasnet_v1se_4.0.onnx
"""
from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from minifasnet_arch import MiniFASNetV1SE, MiniFASNetV2  # noqa: E402

HERE = Path(__file__).parent
KERNEL = ((80 + 15) // 16, (80 + 15) // 16)  # get_kernel(80, 80) -> (5, 5)

MODELS = [
    ("2.7_80x80_MiniFASNetV2.pth", MiniFASNetV2, "minifasnet_v2_2.7.onnx"),
    ("4_0_0_80x80_MiniFASNetV1SE.pth", MiniFASNetV1SE, "minifasnet_v1se_4.0.onnx"),
]


def load(pth: Path, ctor):
    model = ctor(conv6_kernel=KERNEL)
    sd = torch.load(pth, map_location="cpu")
    if next(iter(sd)).startswith("module."):
        sd = OrderedDict((k[7:], v) for k, v in sd.items())
    model.load_state_dict(sd)
    model.eval()
    return model


if __name__ == "__main__":
    for pth_name, ctor, out_name in MODELS:
        model = load(HERE / pth_name, ctor)
        dummy = torch.zeros(1, 3, 80, 80)
        torch.onnx.export(
            model,
            dummy,
            str(HERE / out_name),
            input_names=["input"],
            output_names=["logits"],
            opset_version=11,
            dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
            dynamo=False,
        )
        print("wrote", out_name)
