# CVPR-2024 FAS challenge model (second anti-spoof gate)

Source: https://github.com/Xianhua-He/cvpr2024-face-anti-spoofing-challenge (MIT). Weights `full_resnet50.pth`
are hosted on the authors' Google Drive. Files in this folder are git-ignored; regenerate with:

```bash
uv run --with gdown --with torch --with onnx --with onnxscript python weights/convert_cvpr.py
# -> weights/cvpr2024/resnet50.onnx (94 MB), input 1x3x224x224 RGB ImageNet-normalised, output softmax [live, spoof]
```

Measured 2026-09-17 on a face crop (box + 30 % margin): live >= 0.30 (webcam >= 0.81), phone-screen replay <= 0.015, including
frames where no phone bezel is visible (which fool MiniFASNet). Full-frame input is NOT reliable; keep the crop.
Set `CVPR_ENABLED=0` to run without it.
