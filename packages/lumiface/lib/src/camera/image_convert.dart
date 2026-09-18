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

/// Converts a raw frame to an upright JPEG whose long side is at most [maxSide]
/// (the server detects at 640; a 720p frame is subsampled 2x, which is also what
/// keeps 8 fps affordable on a phone). Pure function, safe for `compute`.
Uint8List rawFrameToJpeg(RawFrame f, {int quality = 90, int maxSide = 640}) {
  final long = f.width > f.height ? f.width : f.height;
  final step = long <= maxSide ? 1 : (long + maxSide - 1) ~/ maxSide;
  final w = f.width ~/ step, h = f.height ~/ step;
  final rgb = Uint8List(w * h * 3);
  switch (f.format) {
    case 'bgra8888':
      _bgraToRgb(f, rgb, w, h, step);
    case 'nv21':
      _nv21ToRgb(f, rgb, w, h, step);
    case 'yuv420':
      _yuv420ToRgb(f, rgb, w, h, step);
    default:
      throw UnsupportedError('frame format ${f.format}');
  }
  var image = img.Image.fromBytes(width: w, height: h, bytes: rgb.buffer, numChannels: 3);
  if (f.rotationDegrees % 360 != 0) {
    image = img.copyRotate(image, angle: f.rotationDegrees);
  }
  if (f.mirror) image = img.flipHorizontal(image);
  return img.encodeJpg(image, quality: quality);
}

void _bgraToRgb(RawFrame f, Uint8List out, int w, int h, int step) {
  final src = f.planes[0];
  final stride = f.bytesPerRow[0];
  var o = 0;
  for (var row = 0; row < h; row++) {
    var i = row * step * stride;
    for (var col = 0; col < w; col++, i += 4 * step) {
      out[o++] = src[i + 2];
      out[o++] = src[i + 1];
      out[o++] = src[i];
    }
  }
}

void _nv21ToRgb(RawFrame f, Uint8List out, int w, int h, int step) {
  final y = f.planes[0];
  final yStride = f.bytesPerRow[0];
  final vuOffset = yStride * f.height;
  var o = 0;
  for (var row = 0; row < h; row++) {
    final sy = row * step;
    final yRow = sy * yStride;
    final vuRow = vuOffset + (sy >> 1) * yStride;
    for (var col = 0; col < w; col++) {
      final sx = col * step;
      final vuIdx = vuRow + (sx & ~1);
      o = _putYuv(out, o, y[yRow + sx], y[vuIdx + 1], y[vuIdx]);
    }
  }
}

void _yuv420ToRgb(RawFrame f, Uint8List out, int w, int h, int step) {
  final y = f.planes[0], u = f.planes[1], v = f.planes[2];
  final yStride = f.bytesPerRow[0], uvStride = f.bytesPerRow[1];
  final uvPixel = f.bytesPerPixel[1];
  var o = 0;
  for (var row = 0; row < h; row++) {
    final sy = row * step;
    final yRow = sy * yStride;
    final uvRow = (sy >> 1) * uvStride;
    for (var col = 0; col < w; col++) {
      final sx = col * step;
      final uvIdx = uvRow + (sx >> 1) * uvPixel;
      o = _putYuv(out, o, y[yRow + sx], u[uvIdx], v[uvIdx]);
    }
  }
}

int _putYuv(Uint8List out, int o, int yy, int u, int v) {
  final c = yy - 16, d = u - 128, e = v - 128;
  out[o] = ((298 * c + 409 * e + 128) >> 8).clamp(0, 255);
  out[o + 1] = ((298 * c - 100 * d - 208 * e + 128) >> 8).clamp(0, 255);
  out[o + 2] = ((298 * c + 516 * d + 128) >> 8).clamp(0, 255);
  return o + 3;
}
