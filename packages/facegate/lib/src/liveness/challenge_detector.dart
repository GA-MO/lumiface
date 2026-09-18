import '../models.dart';
import 'config.dart';

/// Per-challenge detector fed with [FaceSignal]s. Returns true once the
/// challenge is satisfied. Detectors are single-use.
abstract class ChallengeDetector {
  ChallengeDetector(this.config);

  final LivenessConfig config;

  bool feed(FaceSignal s);

  static ChallengeDetector forChallenge(Challenge c, LivenessConfig config) => switch (c) {
        Challenge.blink => BlinkDetector(config),
        Challenge.smile => SmileDetector(config),
        Challenge.turnLeft => TurnDetector(config, left: true),
        Challenge.turnRight => TurnDetector(config, left: false),
        Challenge.nod => NodDetector(config),
      };
}

/// open -> closed (40..600 ms) -> open. A closed phase that lasts too long
/// (photo with eyes shut, slow video) resets the detector.
class BlinkDetector extends ChallengeDetector {
  BlinkDetector(super.config);

  bool _seenOpen = false;
  int? _closedAt;

  @override
  bool feed(FaceSignal s) {
    final e = s.eyeOpen;
    if (e == null) return false;
    if (_closedAt == null) {
      if (e >= config.eyeOpenThreshold) _seenOpen = true;
      if (_seenOpen && e <= config.eyeClosedThreshold) _closedAt = s.tsMs;
      return false;
    }
    final closedFor = s.tsMs - _closedAt!;
    if (closedFor > config.blinkMaxMs) {
      _closedAt = null;
      _seenOpen = false;
      return false;
    }
    if (e >= config.eyeOpenThreshold) {
      if (closedFor >= config.blinkMinMs) return true;
      _closedAt = null;
    }
    return false;
  }
}

/// Requires a non-smiling baseline first, then smile >= threshold held for smileHoldMs.
class SmileDetector extends ChallengeDetector {
  SmileDetector(super.config);

  bool _baseline = false;
  int? _smilingSince;

  @override
  bool feed(FaceSignal s) {
    final v = s.smile;
    if (v == null) return false;
    if (!_baseline) {
      if (v <= config.smileBaselineMax) _baseline = true;
      return false;
    }
    if (v >= config.smileThreshold) {
      _smilingSince ??= s.tsMs;
      return s.tsMs - _smilingSince! >= config.smileHoldMs;
    }
    _smilingSince = null;
    return false;
  }
}

/// Yaw beyond turnMinYaw in the requested direction, held for turnHoldMs,
/// and (parallaxMinShift > 0) the nose must have moved relative to the eyes
/// since the frontal baseline, which a rotated flat picture cannot do.
/// Positive yaw == user's own left (signal sources normalise this).
class TurnDetector extends ChallengeDetector {
  TurnDetector(super.config, {required this.left});

  final bool left;
  int? _since;
  double? _baseline;

  bool get _needParallax => config.parallaxMinShift > 0;

  @override
  bool feed(FaceSignal s) {
    final yaw = s.yaw;
    if (yaw == null) return false;
    if (_needParallax && yaw.abs() <= config.neutralMaxYaw) {
      _baseline = s.noseParallax ?? _baseline;
    }
    final dirOk = left ? yaw >= config.turnMinYaw : yaw <= -config.turnMinYaw;
    if (!dirOk) {
      _since = null;
      return false;
    }
    if (_needParallax) {
      final p = s.noseParallax;
      if (_baseline == null || p == null || (p - _baseline!).abs() < config.parallaxMinShift) {
        _since = null;
        return false;
      }
    }
    _since ??= s.tsMs;
    return s.tsMs - _since! >= config.turnHoldMs;
  }
}

/// |pitch| beyond nodMinPitch (either direction) held for nodHoldMs.
class NodDetector extends ChallengeDetector {
  NodDetector(super.config);

  int? _since;

  @override
  bool feed(FaceSignal s) {
    final p = s.pitch;
    if (p == null) return false;
    if (p.abs() < config.nodMinPitch) {
      _since = null;
      return false;
    }
    _since ??= s.tsMs;
    return s.tsMs - _since! >= config.nodHoldMs;
  }
}
