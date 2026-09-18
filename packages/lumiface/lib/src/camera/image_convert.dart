import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// Raw camera frame description that can cross an isolate boundary.
class RawFrame {
  const RawFrame({
    required this.width,
    required this.height,
    required this.format, // 'bgra8888' | 'nv21' | 'yuv420'
    required this.planes,
    required this.bytesPerRow,
    required this.bytesPerPixel,
    required this.rotationDegrees,
    this.mirror = false,
  });

  final int width;
  final int height;
  final String format;
  final List<Uint8List> planes;
  final List<int> bytesPerRow;
  final List<int> bytesPerPixel;
  final int rotationDegrees;
  final bool mirror;
}

/// Converts a raw frame to an upright JPEG. Pure function, safe for `compute`.
Uint8List rawFrameToJpeg(RawFrame f, {int quality = 90}) {
  img.Image image;
  switch (f.format) {
    case 'bgra8888':
      image = img.Image.fromBytes(
        width: f.width,
        height: f.height,
        bytes: f.planes[0].buffer,
        bytesOffset: f.planes[0].offsetInBytes,
        rowStride: f.bytesPerRow[0],
        numChannels: 4,
        order: img.ChannelOrder.bgra,
      );
    case 'nv21':
      image = _nv21ToImage(f);
    case 'yuv420':
      image = _yuv420ToImage(f);
    default:
      throw UnsupportedError('frame format ${f.format}');
  }
  if (f.rotationDegrees % 360 != 0) {
    image = img.copyRotate(image, angle: f.rotationDegrees);
  }
  if (f.mirror) image = img.flipHorizontal(image);
  return img.encodeJpg(image, quality: quality);
}

img.Image _nv21ToImage(RawFrame f) {
  final w = f.width, h = f.height;
  final y = f.planes[0];
  final yStride = f.bytesPerRow[0];
  final vuOffset = yStride * h;
  final out = img.Image(width: w, height: h, numChannels: 3);
  for (var row = 0; row < h; row++) {
    final vuRow = vuOffset + (row >> 1) * yStride;
    for (var col = 0; col < w; col++) {
      final yy = y[row * yStride + col];
      final vuIdx = vuRow + (col & ~1);
      final v = y[vuIdx];
      final u = y[vuIdx + 1];
      _setYuv(out, col, row, yy, u, v);
    }
  }
  return out;
}

img.Image _yuv420ToImage(RawFrame f) {
  final w = f.width, h = f.height;
  final y = f.planes[0], u = f.planes[1], v = f.planes[2];
  final yStride = f.bytesPerRow[0], uvStride = f.bytesPerRow[1];
  final uvPixel = f.bytesPerPixel[1];
  final out = img.Image(width: w, height: h, numChannels: 3);
  for (var row = 0; row < h; row++) {
    for (var col = 0; col < w; col++) {
      final uvIdx = (row >> 1) * uvStride + (col >> 1) * uvPixel;
      _setYuv(out, col, row, y[row * yStride + col], u[uvIdx], v[uvIdx]);
    }
  }
  return out;
}

void _setYuv(img.Image out, int x, int y, int yy, int u, int v) {
  final c = yy - 16, d = u - 128, e = v - 128;
  final r = (298 * c + 409 * e + 128) >> 8;
  final g = (298 * c - 100 * d - 208 * e + 128) >> 8;
  final b = (298 * c + 516 * d + 128) >> 8;
  out.setPixelRgb(x, y, r.clamp(0, 255), g.clamp(0, 255), b.clamp(0, 255));
}
