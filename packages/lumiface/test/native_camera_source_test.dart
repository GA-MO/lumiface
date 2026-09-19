import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:lumiface/src/camera/native_camera_source.dart';

void main() {
  test('the largest box becomes the signal, angles come with it when the detector has them', () {
    final s = NativeCameraSource.signalFromFaces([
      {'left': 0.1, 'top': 0.1, 'width': 0.2, 'height': 0.2},
      {'left': 0.3, 'top': 0.2, 'width': 0.5, 'height': 0.5, 'yaw': 12.5, 'pitch': -3.0},
    ], 42);
    expect(s.tsMs, 42);
    expect(s.faceCount, 2);
    expect(s.box, const Rect.fromLTWH(0.3, 0.2, 0.5, 0.5));
    expect(s.yaw, 12.5);
    expect(s.pitch, -3.0);
    final none = NativeCameraSource.signalFromFaces(const [], 43);
    expect(none.present, false);
    final blaze = NativeCameraSource.signalFromFaces([{'left': 0.1, 'top': 0.1, 'width': 0.2, 'height': 0.2}], 44);
    expect(blaze.present, true);
    expect(blaze.yaw, isNull);
  });
}
