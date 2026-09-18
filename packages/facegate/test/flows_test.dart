import 'package:facegate/facegate.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

Future<void> pump() => Future<void>.delayed(Duration.zero);

void main() {
  late FakeSource src;
  late FakeApi api;

  setUp(() {
    src = FakeSource();
    api = FakeApi([Challenge.blink, Challenge.smile]);
  });

  Future<void> emit(FaceSignal s) async {
    src.emit(s);
    await pump();
    await pump();
  }

  group('LivenessConfig json', () {
    test('round-trips every field and keeps defaults for missing keys', () {
      const original = LivenessConfig(alignHoldMs: 900, parallaxMinShift: 0.12, parallaxWhenNoTurn: false);
      final json = original.toJson();
      expect(json.length, 23);
      final back = LivenessConfig.fromJson(json);
      expect(back.alignHoldMs, 900);
      expect(back.parallaxMinShift, 0.12);
      expect(back.parallaxWhenNoTurn, false);
      expect(back.toJson(), json);
      final partial = LivenessConfig.fromJson({'blink_max_ms': 900});
      expect(partial.blinkMaxMs, 900);
      expect(partial.smileThreshold, const LivenessConfig().smileThreshold);
    });

    test('FaceSession parses client_config and mode', () {
      final s = FaceSession.fromJson({
        'session_id': 'x',
        'mode': 'liveness',
        'purpose': 'kiosk',
        'challenges': ['smile'],
        'frame_kinds': ['neutral_start', 'challenge_0', 'neutral_end'],
        'ttl_seconds': 60,
        'flash_colors': ['ff0000'],
        'flash_hold_ms': 500,
        'client_config': {'challenge_timeout_ms': 4000},
      });
      expect(s.mode, 'liveness');
      expect(s.clientConfig!.challengeTimeoutMs, 4000);
      expect(s.flashColors.single.toARGB32(), 0xFFFF0000);
    });
  });

  group('FaceVerifyController', () {
    test('uses the session client_config when no explicit config is given', () async {
      api.sessionConfig = const LivenessConfig(alignHoldMs: 2000, parallaxWhenNoTurn: false);
      final c = FaceVerifyController(source: src, capturer: src, client: api, subjectId: 'E001');
      await c.start();
      await pump();
      expect(c.config.alignHoldMs, 2000);
      expect(c.state.value.challengeCount, 2);
      await emit(neutral(0));
      await emit(neutral(700));
      expect(c.state.value.phase, LivenessPhase.aligning);
      await emit(neutral(2100));
      expect(c.state.value.phase, LivenessPhase.challenge);
      c.dispose();
    });

    test('explicit config wins over the session', () async {
      api.sessionConfig = const LivenessConfig(alignHoldMs: 2000);
      final c = FaceVerifyController(
          source: src, capturer: src, client: api, subjectId: 'E001', config: const LivenessConfig(alignHoldMs: 100));
      await c.start();
      await pump();
      expect(c.config.alignHoldMs, 100);
      c.dispose();
    });

    test('liveness flow sends no subject and a purpose', () async {
      final c = FaceVerifyController(source: src, capturer: src, client: api, purpose: 'kiosk');
      expect(c.flow, FaceFlow.liveness);
      await c.start();
      await pump();
      expect(api.lastSubjectId, isNull);
      expect(api.lastPurpose, 'kiosk');
      c.dispose();
    });

    test('progress climbs from align to success', () async {
      final c = FaceVerifyController(
          source: src, capturer: src, client: api, subjectId: 'E001',
          config: const LivenessConfig(parallaxWhenNoTurn: false));
      await c.start();
      await pump();
      expect(c.state.value.progress, 0);
      await emit(neutral(0));
      await emit(neutral(700));
      expect(c.state.value.progress, closeTo(0.5 / 3, 1e-9));
      c.dispose();
    });
  });

  group('FaceEnrollController', () {
    test('aligns, captures one frame and enrols', () async {
      final c = FaceEnrollController(source: src, capturer: src, client: api, externalId: 'E9', name: 'Nine');
      expect(c.flow, FaceFlow.enroll);
      await c.start();
      expect(c.state.value.phase, LivenessPhase.aligning);
      await emit(FaceSignal.none(0));
      expect(c.state.value.hint, AlignHint.noFace);
      await emit(neutral(100));
      expect(c.state.value.hint, AlignHint.holdStill);
      await emit(neutral(800));
      await pump();
      expect(c.state.value.phase, LivenessPhase.success);
      expect(c.state.value.result!.subject!.externalId, 'E9');
      expect(c.state.value.result!.subject!.name, 'Nine');
      expect(src.captures, 1);
      expect(api.enrollCalls, 1);
      c.dispose();
    });

    test('server rejection becomes a failed result with the reason code', () async {
      final c = FaceEnrollController(source: src, capturer: src, client: api, externalId: 'REJECT');
      await c.start();
      await emit(neutral(0));
      await emit(neutral(700));
      await pump();
      expect(c.state.value.phase, LivenessPhase.failed);
      expect(c.state.value.result!.reasonCode, 'POSE_NOT_FRONTAL');
      c.dispose();
    });

    test('cancel', () async {
      final c = FaceEnrollController(source: src, capturer: src, client: api, externalId: 'E9');
      await c.start();
      c.cancel();
      expect(c.state.value.result!.reasonCode, 'CANCELLED');
      c.dispose();
    });
  });

  group('LivenessStrings', () {
    test('messageFor picks the success line per flow and copyWith merges reasons', () {
      const done = LivenessState(phase: LivenessPhase.success);
      expect(LivenessStrings.en.messageFor(done, FaceFlow.verify), 'Verified');
      expect(LivenessStrings.en.messageFor(done, FaceFlow.liveness), 'Live person confirmed');
      expect(LivenessStrings.en.messageFor(done, FaceFlow.enroll), 'Photo enrolled');
      final custom = LivenessStrings.en.copyWith(success: 'Door open', reasons: {'NO_MATCH': 'Nope'});
      expect(custom.messageFor(done, FaceFlow.verify), 'Door open');
      expect(custom.reason('NO_MATCH'), 'Nope');
      expect(custom.reason('SPOOF'), LivenessStrings.en.reason('SPOOF'));
    });
  });
}
