import 'dart:typed_data';

import 'package:facegate/facegate.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

void main() {
  test('bgra frame with row padding converts and rotates', () {
    const w = 4, h = 2, stride = 24; // 4px*4B = 16, padded to 24
    final bytes = Uint8List(stride * h);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final o = y * stride + x * 4;
        bytes[o] = 255; // B
        bytes[o + 1] = 0;
        bytes[o + 2] = x == 0 ? 255 : 0; // R on first column
        bytes[o + 3] = 255;
      }
    }
    final jpeg = rawFrameToJpeg(RawFrame(
      width: w, height: h, format: 'bgra8888', planes: [bytes], bytesPerRow: [stride], bytesPerPixel: [4],
      rotationDegrees: 90,
    ), quality: 100);
    final out = img.decodeJpg(jpeg)!;
    expect(out.width, h);
    expect(out.height, w);
  });

  test('nv21 frame converts', () {
    const w = 4, h = 4;
    final bytes = Uint8List(w * h + (w * h ~/ 2));
    bytes.fillRange(0, w * h, 235); // bright Y
    bytes.fillRange(w * h, bytes.length, 128); // neutral chroma
    final jpeg = rawFrameToJpeg(RawFrame(
      width: w, height: h, format: 'nv21', planes: [bytes], bytesPerRow: [w], bytesPerPixel: [1],
      rotationDegrees: 0,
    ), quality: 100);
    final out = img.decodeJpg(jpeg)!;
    final p = out.getPixel(1, 1);
    expect(p.r > 240 && p.g > 240 && p.b > 240, true);
  });
}
