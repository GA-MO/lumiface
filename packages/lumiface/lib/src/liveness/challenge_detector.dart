import 'dart:ui' show Rect;

import '../models.dart';
import 'config.dart';

/// Per-challenge detector fed with [FaceSignal]s. Returns true once the
/// challenge is satisfied. Detectors are single-use.
abstract class ChallengeDetector {
  ChallengeDetector(this.config);

  final LivenessConfig config;

  bool feed(FaceSignal s);

  static const defaultOval = Rect.fromLTWH(0.19, 0.2, 0.62, 0.5);

  static ChallengeDetector forChallenge(Challenge c, LivenessConfig config, {Rect? oval}) => switch (c) {
        Challenge.faceMove => FaceMoveDetector(config, oval: oval ?? defaultOval),
      };
}

/// Start far (face narrower than `moveStartMaxRatio` of the oval), move closer until the face box is
/// `ovalMinFill` of the oval's width and centred within a fifth of it, hold for `ovalHoldMs`. [oval]
/// and the boxes are in frame-normalised coordinates. [hint] says what the person should do next;
/// null while approaching, when the challenge text itself is the instruction.
class FaceMoveDetector extends ChallengeDetector {
  FaceMoveDetector(super.config, {required this.oval});

  final Rect oval;
  bool _startedFar = false;
  int? _fittedSince;
  AlignHint? hint;

  @override
  bool feed(FaceSignal s) {
    final b = s.box;
    if (b == null) return false;
    if (!_startedFar) {
      if (b.width > oval.width * config.moveStartMaxRatio) {
        hint = AlignHint.tooClose;
        return false;
      }
      _startedFar = true;
    }
    final filled = b.width >= oval.width * config.ovalMinFill;
    final offCentre = (b.center.dx - oval.center.dx).abs() > oval.width * 0.2 ||
        (b.center.dy - oval.center.dy).abs() > oval.height * 0.2;
    if (filled && !offCentre) {
      hint = AlignHint.holdStill;
      _fittedSince ??= s.tsMs;
      return s.tsMs - _fittedSince! >= config.ovalHoldMs;
    }
    _fittedSince = null;
    hint = filled && offCentre ? AlignHint.notCentered : null;
    return false;
  }
}

