import 'dart:ui';

import 'package:lumiface/lumiface.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

Future<void> pump() => Future<void>.delayed(Duration.zero);

void main() {
  late FakeSource src;
  late FakeApi api;
  late FaceVerifyController c;

  Future<void> boot(
    List<Challenge> ch, {
    VerifyResult? response,
    LivenessConfig config = const LivenessConfig(),
    List<Color> flashColors = const [],
    OvalTarget? oval,
  }) async {
    src = FakeSource();
    api = FakeApi(ch, response: response, flashColors: flashColors, oval: oval);
    c = FaceVerifyController(source: src, recorder: src, client: api, sessionProvider: api.createSession, config: config);
    await c.start();
    await pump();
  }

  Future<void> emit(FaceSignal s) async {
    src.emit(s);
    await pump();
    await pump();
  }

  /// Hold a neutral face long enough to pass alignment (starts at [t]).
  Future<int> align(int t) async {
    await emit(neutral(t));
    await emit(neutral(t + 700));
    expect(c.state.value.phase, LivenessPhase.challenge);
    return t + 700;
  }

  /// Far, then into the default oval, held for the configured time.
  Future<int> doMove(int t) async {
    await emit(neutral(t, width: 0.3));
    await emit(neutral(t + 300, width: 0.6));
    await emit(neutral(t + 900, width: 0.6));
    return t + 900;
  }

  tearDown(() => c.dispose());

  test('screen flash: a flash event per colour after the challenges, then flash_end', () async {
    const colors = [Color(0xFFFF0000), Color(0xFF00FF00), Color(0xFF0000FF)];
    await boot([Challenge.faceMove], flashColors: colors);
    var t = await align(0);
    t = await doMove(t + 100);
    // settle passed and frontal again -> flash starts instead of neutral_end
    await emit(neutral(t + 500));
    expect(c.state.value.phase, LivenessPhase.flash);
    expect(c.state.value.flashColor, colors[0]);
    expect(c.state.value.flashIndex, 0);
    // too early: the colour stays up until flash_hold_ms
    await emit(neutral(t + 700));
    expect(c.state.value.flashColor, colors[0]);
    await emit(neutral(t + 1000));
    expect(c.state.value.flashColor, colors[1]);
    await emit(neutral(t + 1500));
    expect(c.state.value.flashColor, colors[2]);
    await emit(neutral(t + 2000));
    expect(c.state.value.phase, LivenessPhase.challenge);
    expect(c.state.value.flashColor, isNull);
    // tint must clear before the end: the settle window keeps streaming, nothing ends early
    await emit(neutral(t + 2300));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(neutral(t + 2900));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentEvents.map((e) => '${e.$1.name}${e.$3 ?? ''}'),
        ['aligned', 'challengeDone0', 'flash0', 'flash1', 'flash2', 'flashEnd']);
    expect(api.ended, true);
  });

  test('screen flash: face lost during flash fails', () async {
    await boot([Challenge.faceMove], flashColors: const [Color(0xFFFF0000)]);
    var t = await align(0);
    t = await doMove(t + 100);
    await emit(neutral(t + 500));
    expect(c.state.value.phase, LivenessPhase.flash);
    await emit(FaceSignal.none(t + 600));
    await emit(FaceSignal.none(t + 2200));
    expect(c.state.value.result!.reasonCode, 'FACE_LOST');
  });

  test('face_move: start far, move into the oval, hold; the guide shows the oval', () async {
    await boot([Challenge.faceMove], oval: const OvalTarget(cx: 0.5, cy: 0.45, width: 0.62, heightRatio: 1.35));
    c.frameAspect = 0.75;
    Rect at(double w) => Rect.fromCenter(center: const Offset(0.5, 0.45), width: w, height: w * 1.35 * 0.75);
    await emit(neutral(0).copyWith(box: at(0.55)));
    expect(c.state.value.hint, AlignHint.tooClose, reason: 'too close is said while aligning');
    await emit(neutral(100).copyWith(box: at(0.45)));
    await emit(neutral(800).copyWith(box: at(0.45)));
    expect(c.state.value.phase, LivenessPhase.challenge);
    const t = 800;
    expect(c.state.value.challenge, Challenge.faceMove);
    expect(c.state.value.target, isNotNull);
    expect(c.state.value.target!.width, closeTo(0.62, 1e-9));
    await emit(neutral(t + 200).copyWith(box: at(0.45)));
    expect(c.state.value.hint, isNull, reason: 'the aligned distance is a valid start: the challenge text says move closer');
    await emit(neutral(t + 300).copyWith(box: at(0.6).shift(const Offset(0.2, 0))));
    expect(c.state.value.hint, AlignHint.notCentered);
    await emit(neutral(t + 400).copyWith(box: at(0.6)));
    expect(c.state.value.hint, AlignHint.holdStill);
    await emit(neutral(t + 700).copyWith(box: at(0.6)));
    await emit(neutral(t + 1000).copyWith(box: at(0.6)));
    await emit(neutral(t + 1500).copyWith(box: at(0.6)));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentEvents.map((e) => e.$1), [StreamEventName.aligned, StreamEventName.challengeDone]);
  });

  test('happy path: the recording runs from the plan to the end, events at each boundary, success', () async {
    await boot([Challenge.faceMove]);
    expect(c.state.value.phase, LivenessPhase.aligning);
    expect(c.state.value.challengeCount, 1);
    expect(api.format, StreamFormat.h264);
    expect(src.recording, true);
    src.chunk(0);

    var t = await align(1000);
    src.chunk(t);
    expect(c.state.value.challenge, Challenge.faceMove);
    t = await doMove(t + 200);
    src.chunk(t);
    await emit(neutral(t + 500, width: 0.6));
    await pump();

    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentEvents.map((e) => e.$1), [StreamEventName.aligned, StreamEventName.challengeDone]);
    expect(api.sentEvents.map((e) => e.$3), [null, 0]);
    final ts = api.sentEvents.map((e) => e.$2).toList();
    expect(ts[1] - ts[0], greaterThanOrEqualTo(300));
    expect(api.ended, true);
    // Every chunk the recorder cut while the flow ran went up; the recorder stopped before the verdict.
    expect(api.sentChunks, [0, 1700, t]);
    expect(src.recording, false);
    expect(src.recordings, 1);
    src.chunk(t + 900);
    expect(api.sentChunks.length, 3);
  });

  test('alignment hints', () async {
    await boot([Challenge.faceMove]);
    await emit(FaceSignal.none(0));
    expect(c.state.value.hint, AlignHint.noFace);
    await emit(FaceSignal(tsMs: 10, faceCount: 1, box: const Rect.fromLTWH(0.4, 0.4, 0.15, 0.2)));
    expect(c.state.value.hint, AlignHint.tooFar);
    await emit(FaceSignal(tsMs: 20, faceCount: 1, box: const Rect.fromLTWH(0.0, 0.3, 0.4, 0.45)));
    expect(c.state.value.hint, AlignHint.notCentered);
    await emit(neutral(30, yaw: 40));
    expect(c.state.value.hint, AlignHint.lookStraight);
    await emit(FaceSignal(tsMs: 40, faceCount: 2, box: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.45)));
    expect(c.state.value.hint, AlignHint.multipleFaces);
    await emit(neutral(50));
    expect(c.state.value.hint, AlignHint.holdStill);
    expect(c.state.value.phase, LivenessPhase.aligning);
  });

  test('too close is said while aligning, so the walk starts from where the person held still', () async {
    await boot([Challenge.faceMove]);
    await emit(neutral(0, width: 0.6));
    expect(c.state.value.phase, LivenessPhase.aligning);
    expect(c.state.value.hint, AlignHint.tooClose);
    final t = await align(100);
    expect(c.state.value.hint, isNull);
    await emit(neutral(t + 100, width: 0.6));
    expect(c.state.value.hint, AlignHint.holdStill);
  });

  test('standing still without the walk does not pass; timeout fails', () async {
    await boot([Challenge.faceMove]);
    final t = await align(0);
    await emit(neutral(t + 1500));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(neutral(t + 11000));
    expect(c.state.value.phase, LivenessPhase.failed);
    expect(c.state.value.result!.reasonCode, 'TIMEOUT');
  });

  test('face lost during challenge fails', () async {
    await boot([Challenge.faceMove]);
    final t = await align(0);
    await emit(FaceSignal.none(t + 500));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(FaceSignal.none(t + 2300));
    expect(c.state.value.result!.reasonCode, 'FACE_LOST');
  });

  test('server rejection propagates', () async {
    await boot([Challenge.faceMove], response: const VerifyResult(ok: false, reasonCode: 'SPOOF'));
    var t = await align(0);
    t = await doMove(t + 100);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.value.phase, LivenessPhase.failed);
    expect(c.state.value.result!.reasonCode, 'SPOOF');
  });

  test('neutral_end waits until the face is frontal again (a detector that reports angles)', () async {
    await boot([Challenge.faceMove]);
    var t = await align(0);
    t = await doMove(t + 100);
    // settle passed but turned away: must not upload yet
    await emit(neutral(t + 500, yaw: 30));
    expect(c.state.value.phase, LivenessPhase.challenge);
    expect(c.state.value.hint, AlignHint.lookStraight);
    await emit(neutral(t + 600));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.ended, true);
  });

  test('cancel stops the recorder', () async {
    await boot([Challenge.faceMove]);
    expect(src.recording, true);
    c.cancel();
    expect(c.state.value.result!.reasonCode, 'CANCELLED');
    expect(src.recording, false);
  });
}
