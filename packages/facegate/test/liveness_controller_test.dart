import 'dart:ui';

import 'package:facegate/facegate.dart';
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
  }) async {
    src = FakeSource();
    api = FakeApi(ch, response: response, flashColors: flashColors);
    c = FaceVerifyController(source: src, capturer: src, client: api, subjectId: 'E001', config: config);
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

  Future<int> doBlink(int t) async {
    await emit(neutral(t));
    await emit(neutral(t + 100, eye: 0.1));
    await emit(neutral(t + 250, eye: 0.95));
    return t + 250;
  }

  Future<int> doSmile(int t) async {
    await emit(neutral(t, smile: 0.1));
    await emit(neutral(t + 100, smile: 0.9));
    await emit(neutral(t + 500, smile: 0.9));
    return t + 500;
  }

  tearDown(() => c.dispose());

  Future<int> doTurn(int t) async {
    final left = c.state.value.challenge == Challenge.turnLeft;
    final yaw = left ? 30.0 : -30.0;
    await emit(neutral(t));
    await emit(neutral(t + 100, yaw: yaw));
    await emit(neutral(t + 400, yaw: yaw));
    return t + 400;
  }

  test('screen flash: one frame per colour after the challenges, before neutral_end', () async {
    const colors = [Color(0xFFFF0000), Color(0xFF00FF00), Color(0xFF0000FF)];
    await boot([Challenge.turnLeft], flashColors: colors);
    var t = await align(0);
    t = await doTurn(t + 100);
    // settle passed and frontal again -> flash starts instead of neutral_end
    await emit(neutral(t + 500));
    expect(c.state.value.phase, LivenessPhase.flash);
    expect(c.state.value.flashColor, colors[0]);
    expect(c.state.value.flashIndex, 0);
    // too early: nothing captured yet
    await emit(neutral(t + 700));
    expect(src.captures, 2);
    await emit(neutral(t + 1000));
    expect(src.captures, 3);
    expect(c.state.value.flashColor, colors[1]);
    await emit(neutral(t + 1500));
    expect(c.state.value.flashColor, colors[2]);
    await emit(neutral(t + 2000));
    expect(c.state.value.phase, LivenessPhase.challenge);
    expect(c.state.value.flashColor, isNull);
    // tint must clear before neutral_end: nothing uploaded during the settle window
    await emit(neutral(t + 2300));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(neutral(t + 2900));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentFrames!.map((f) => f.kind),
        ['neutral_start', 'challenge_0', 'flash_0', 'flash_1', 'flash_2', 'neutral_end']);
    expect(api.sentDurations!.length, 1);
  });

  test('screen flash: face lost during flash fails', () async {
    await boot([Challenge.blink], flashColors: const [Color(0xFFFF0000)],
        config: const LivenessConfig(parallaxWhenNoTurn: false));
    var t = await align(0);
    t = await doBlink(t + 100);
    await emit(neutral(t + 500));
    expect(c.state.value.phase, LivenessPhase.flash);
    await emit(FaceSignal.none(t + 600));
    await emit(FaceSignal.none(t + 2200));
    expect(c.state.value.result!.reasonCode, 'FACE_LOST');
  });

  test('happy path: blink + smile -> 4 frames uploaded, success', () async {
    await boot([Challenge.blink, Challenge.smile], config: const LivenessConfig(parallaxWhenNoTurn: false));
    expect(c.state.value.phase, LivenessPhase.aligning);
    expect(c.state.value.challengeCount, 2);

    var t = await align(1000);
    expect(c.state.value.challenge, Challenge.blink);
    t = await doBlink(t + 200);
    // settle window, then next challenge
    await emit(neutral(t + 500));
    expect(c.state.value.challenge, Challenge.smile);
    expect(c.state.value.challengeIndex, 1);
    t = await doSmile(t + 600);
    await emit(neutral(t + 500));
    await pump();

    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentFrames!.map((f) => f.kind), ['neutral_start', 'challenge_0', 'challenge_1', 'neutral_end']);
    expect(api.sentDurations!.length, 2);
    expect(api.sentDurations!.every((d) => d >= 300), true);
    expect(src.captures, 4);
  });

  test('no turn from server -> client-only turn appended, nothing extra uploaded', () async {
    await boot([Challenge.blink, Challenge.smile]);
    expect(c.state.value.challengeCount, 3);
    var t = await align(1000);
    t = await doBlink(t + 200);
    await emit(neutral(t + 500));
    t = await doSmile(t + 600);
    await emit(neutral(t + 500));
    expect(c.state.value.challengeIndex, 2);
    expect([Challenge.turnLeft, Challenge.turnRight], contains(c.state.value.challenge));
    expect(c.state.value.phase, LivenessPhase.challenge);

    // A flat picture "turning" never satisfies the extra turn.
    final yaw = c.state.value.challenge == Challenge.turnLeft ? 30.0 : -30.0;
    await emit(neutral(t + 600, yaw: yaw, flat: true));
    await emit(neutral(t + 1200, yaw: yaw, flat: true));
    expect(c.state.value.phase, LivenessPhase.challenge);

    t = await doTurn(t + 1300);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentFrames!.map((f) => f.kind), ['neutral_start', 'challenge_0', 'challenge_1', 'neutral_end']);
    expect(api.sentDurations!.length, 2);
    expect(src.captures, 4);
  });

  test('server turn: no extra challenge is appended', () async {
    await boot([Challenge.turnRight, Challenge.blink]);
    expect(c.state.value.challengeCount, 2);
    var t = await align(0);
    t = await doTurn(t + 100);
    await emit(neutral(t + 500));
    expect(c.state.value.challenge, Challenge.blink);
    t = await doBlink(t + 600);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentDurations!.length, 2);
  });

  test('alignment hints', () async {
    await boot([Challenge.blink]);
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

  test('slow blink (video) does not pass; timeout fails', () async {
    await boot([Challenge.blink]);
    final t = await align(0);
    await emit(neutral(t + 100));
    await emit(neutral(t + 200, eye: 0.1));
    await emit(neutral(t + 1500, eye: 0.1));
    await emit(neutral(t + 1600, eye: 0.9));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(neutral(t + 11000));
    expect(c.state.value.phase, LivenessPhase.failed);
    expect(c.state.value.result!.reasonCode, 'TIMEOUT');
  });

  test('face lost during challenge fails', () async {
    await boot([Challenge.turnLeft]);
    final t = await align(0);
    await emit(FaceSignal.none(t + 500));
    expect(c.state.value.phase, LivenessPhase.challenge);
    await emit(FaceSignal.none(t + 2300));
    expect(c.state.value.result!.reasonCode, 'FACE_LOST');
  });

  test('server rejection propagates', () async {
    await boot([Challenge.blink],
        response: const VerifyResult(ok: false, reasonCode: 'SPOOF'),
        config: const LivenessConfig(parallaxWhenNoTurn: false));
    var t = await align(0);
    t = await doBlink(t + 100);
    await emit(neutral(t + 500));
    await pump();
    expect(c.state.value.phase, LivenessPhase.failed);
    expect(c.state.value.result!.reasonCode, 'SPOOF');
  });

  test('neutral_end waits until the face is frontal again', () async {
    await boot([Challenge.turnLeft]);
    var t = await align(0);
    await emit(neutral(t + 100, yaw: 30));
    await emit(neutral(t + 400, yaw: 30));
    // settle passed but still turned: must not upload yet
    await emit(neutral(t + 900, yaw: 30));
    expect(c.state.value.phase, LivenessPhase.challenge);
    expect(c.state.value.hint, AlignHint.lookStraight);
    await emit(neutral(t + 1000));
    await pump();
    expect(c.state.value.phase, LivenessPhase.success);
    expect(api.sentFrames!.length, 3);
  });

  test('cancel', () async {
    await boot([Challenge.blink]);
    c.cancel();
    expect(c.state.value.result!.reasonCode, 'CANCELLED');
  });
}
