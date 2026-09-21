import 'package:lumiface/lumiface.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  const cfg = LivenessConfig();

  group('FaceMoveDetector', () {
    test('must start far, then fill the oval centred and hold', () {
      final d = FaceMoveDetector(cfg, oval: ChallengeDetector.defaultOval);
      expect(d.feed(neutral(0, width: 0.5)), false);
      expect(d.hint, AlignHint.tooClose);
      expect(d.feed(neutral(100, width: 0.3)), false);
      expect(d.hint, isNull);
      final off = neutral(200, width: 0.6);
      expect(d.feed(off.copyWith(box: off.box!.shift(const Offset(0.2, 0)))), false);
      expect(d.hint, AlignHint.notCentered);
      expect(d.feed(neutral(300, width: 0.6)), false);
      expect(d.hint, AlignHint.holdStill);
      expect(d.feed(neutral(600, width: 0.6)), false);
      expect(d.feed(neutral(850, width: 0.6)), true);
    });

    test('leaving the oval restarts the hold', () {
      final d = FaceMoveDetector(cfg, oval: ChallengeDetector.defaultOval);
      d.feed(neutral(0, width: 0.3));
      d.feed(neutral(100, width: 0.6));
      d.feed(neutral(400, width: 0.4));
      expect(d.feed(neutral(700, width: 0.6)), false);
      expect(d.feed(neutral(1250, width: 0.6)), true);
    });

    test('a face that was never far does not pass by standing close', () {
      final d = FaceMoveDetector(cfg, oval: ChallengeDetector.defaultOval);
      expect(d.feed(neutral(0, width: 0.6)), false);
      expect(d.feed(neutral(2000, width: 0.6)), false);
      expect(d.hint, AlignHint.tooClose);
    });

    test('no face feeds nothing', () {
      final d = ChallengeDetector.forChallenge(Challenge.faceMove, cfg);
      expect(d.feed(FaceSignal.none(0)), false);
    });
  });
}
