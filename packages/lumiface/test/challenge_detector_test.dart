import 'dart:ui';

import 'package:lumiface/lumiface.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  const cfg = LivenessConfig();

  group('BlinkDetector', () {
    test('open -> closed 120ms -> open succeeds', () {
      final d = BlinkDetector(cfg);
      expect(d.feed(neutral(0)), false);
      expect(d.feed(neutral(100, eye: 0.1)), false);
      expect(d.feed(neutral(220, eye: 0.9)), true);
    });

    test('eyes closed too long resets (photo with shut eyes / slow video)', () {
      final d = BlinkDetector(cfg);
      d.feed(neutral(0));
      d.feed(neutral(100, eye: 0.1));
      expect(d.feed(neutral(900, eye: 0.1)), false);
      expect(d.feed(neutral(950, eye: 0.9)), false, reason: 'must see open baseline again');
      d.feed(neutral(1000));
      d.feed(neutral(1100, eye: 0.1));
      expect(d.feed(neutral(1200, eye: 0.9)), true);
    });

    test('needs an open baseline first', () {
      final d = BlinkDetector(cfg);
      expect(d.feed(neutral(0, eye: 0.1)), false);
      expect(d.feed(neutral(100, eye: 0.9)), false);
    });
  });

  group('SmileDetector', () {
    test('requires non-smiling baseline then hold', () {
      final d = SmileDetector(cfg);
      expect(d.feed(neutral(0, smile: 0.9)), false, reason: 'already smiling: no baseline');
      expect(d.feed(neutral(100, smile: 0.1)), false);
      expect(d.feed(neutral(200, smile: 0.9)), false);
      expect(d.feed(neutral(400, smile: 0.9)), false);
      expect(d.feed(neutral(520, smile: 0.9)), true);
    });
  });

  group('TurnDetector', () {
    test('left needs positive yaw beyond threshold, held', () {
      final d = TurnDetector(cfg, left: true);
      expect(d.feed(neutral(0, yaw: 10)), false);
      expect(d.feed(neutral(100, yaw: -40)), false, reason: 'wrong direction');
      expect(d.feed(neutral(200, yaw: 30)), false);
      expect(d.feed(neutral(450, yaw: 30)), true);
    });

    test('right needs negative yaw', () {
      final d = TurnDetector(cfg, left: false);
      d.feed(neutral(0));
      d.feed(neutral(100, yaw: -30));
      expect(d.feed(neutral(400, yaw: -30)), true);
    });

    test('rotated flat picture (no nose parallax) never passes', () {
      final d = TurnDetector(cfg, left: true);
      expect(d.feed(neutral(0, flat: true)), false);
      expect(d.feed(neutral(100, yaw: 30, flat: true)), false);
      expect(d.feed(neutral(400, yaw: 30, flat: true)), false);
      expect(d.feed(neutral(2000, yaw: 40, flat: true)), false);
    });

    test('needs a frontal baseline before the turn', () {
      final d = TurnDetector(cfg, left: true);
      expect(d.feed(neutral(0, yaw: 30)), false);
      expect(d.feed(neutral(300, yaw: 30)), false, reason: 'no baseline parallax yet');
      d.feed(neutral(400));
      d.feed(neutral(500, yaw: 30));
      expect(d.feed(neutral(800, yaw: 30)), true);
    });

    test('missing landmarks cannot pass; parallaxMinShift=0 restores yaw-only', () {
      final noMarks = FaceSignal(tsMs: 0, faceCount: 1, box: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.45), yaw: 0);
      final turned = FaceSignal(tsMs: 300, faceCount: 1, box: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.45), yaw: 30);
      final strict = TurnDetector(cfg, left: true);
      strict.feed(noMarks);
      strict.feed(turned);
      expect(strict.feed(FaceSignal(tsMs: 600, faceCount: 1, box: turned.box, yaw: 30)), false);

      final loose = TurnDetector(const LivenessConfig(parallaxMinShift: 0), left: true);
      loose.feed(noMarks);
      loose.feed(turned);
      expect(loose.feed(FaceSignal(tsMs: 600, faceCount: 1, box: turned.box, yaw: 30)), true);
    });

    test('noseParallax of the fake face shifts ~0.15 at 25° and 0 when flat', () {
      final p0 = neutral(0).noseParallax!;
      final p25 = neutral(0, yaw: 25).noseParallax!;
      expect((p25 - p0).abs(), closeTo(0.16, 0.03));
      expect((neutral(0, yaw: 25, flat: true).noseParallax! - p0).abs(), lessThan(0.01));
    });
  });

  test('NodDetector accepts either pitch direction', () {
    final d = NodDetector(cfg);
    d.feed(neutral(0, pitch: -20));
    expect(d.feed(neutral(250, pitch: -20)), true);
  });
}
