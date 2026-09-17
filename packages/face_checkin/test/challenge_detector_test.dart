import 'package:face_checkin/face_checkin.dart';
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
      d.feed(neutral(0, yaw: -30));
      expect(d.feed(neutral(300, yaw: -30)), true);
    });
  });

  test('NodDetector accepts either pitch direction', () {
    final d = NodDetector(cfg);
    d.feed(neutral(0, pitch: -20));
    expect(d.feed(neutral(250, pitch: -20)), true);
  });
}
