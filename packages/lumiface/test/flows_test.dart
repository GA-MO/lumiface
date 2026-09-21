import 'package:lumiface/lumiface.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

Future<void> pump() => Future<void>.delayed(Duration.zero);

void main() {
  late FakeSource src;
  late FakeApi api;

  setUp(() {
    src = FakeSource();
    api = FakeApi([Challenge.faceMove]);
  });

  Future<void> emit(FaceSignal s) async {
    src.emit(s);
    await pump();
    await pump();
  }

  group('LivenessConfig json', () {
    test('round-trips every field and keeps defaults for missing keys', () {
      const original = LivenessConfig(alignHoldMs: 900, ovalMinFill: 0.9, moveStartMaxRatio: 0.5);
      final json = original.toJson();
      expect(json.length, 13);
      final back = LivenessConfig.fromJson(json);
      expect(back.alignHoldMs, 900);
      expect(back.ovalMinFill, 0.9);
      expect(back.moveStartMaxRatio, 0.5);
      expect(back.toJson(), json);
      final partial = LivenessConfig.fromJson({'oval_hold_ms': 900});
      expect(partial.ovalHoldMs, 900);
      expect(partial.ovalMinFill, const LivenessConfig().ovalMinFill);
    });

    test('FaceSession parses client_config and mode; StreamPlan the challenges and colours', () {
      final s = FaceSession.fromJson({
        'session_id': 'x',
        'session_token': 't',
        'mode': 'liveness',
        'purpose': 'kiosk',
        'ttl_seconds': 60,
        'client_config': {'challenge_timeout_ms': 4000},
      });
      expect(s.mode, 'liveness');
      expect(s.token, 't');
      expect(s.clientConfig!.challengeTimeoutMs, 4000);
      final p = StreamPlan.fromJson({'challenges': ['face_move'], 'flash_colors': ['ff0000'], 'flash_hold_ms': 500});
      expect(p.challenges, [Challenge.faceMove]);
      expect(p.flashColors.single.toARGB32(), 0xFFFF0000);
      expect(p.flashHoldMs, 500);
    });
  });

  group('FaceVerifyController', () {
    test('uses the session client_config when no explicit config is given', () async {
      api.sessionConfig = const LivenessConfig(alignHoldMs: 2000);
      final c = FaceVerifyController(source: src, recorder: src, client: api, sessionProvider: api.createSession);
      await c.start();
      await pump();
      expect(c.config.alignHoldMs, 2000);
      expect(c.state.value.challengeCount, 1);
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
          source: src, recorder: src, client: api, sessionProvider: api.createSession,
          config: const LivenessConfig(alignHoldMs: 100));
      await c.start();
      await pump();
      expect(c.config.alignHoldMs, 100);
      c.dispose();
    });

    test('the session decides between verify and liveness', () async {
      final c = FaceVerifyController(
          source: src, recorder: src, client: api,
          sessionProvider: () => api.createSession(reference: false, purpose: 'kiosk'));
      expect(c.flow, FaceFlow.verify);
      await c.start();
      await pump();
      expect(c.flow, FaceFlow.liveness);
      expect(api.lastReference, isFalse);
      expect(api.lastPurpose, 'kiosk');
      c.dispose();
    });

    test('a failing session provider ends the flow with NETWORK_ERROR', () async {
      final c = FaceVerifyController(
          source: src, recorder: src, client: api, sessionProvider: () async => throw StateError('backend down'));
      await c.start();
      await pump();
      expect(c.state.value.phase, LivenessPhase.failed);
      expect(c.state.value.result!.reasonCode, 'NETWORK_ERROR');
      c.dispose();
    });

    test('progress climbs from align to success', () async {
      final c = FaceVerifyController(
          source: src, recorder: src, client: api, sessionProvider: api.createSession);
      await c.start();
      await pump();
      expect(c.state.value.progress, 0);
      await emit(neutral(0));
      await emit(neutral(700));
      expect(c.state.value.progress, closeTo(0.5 / 2, 1e-9));
      c.dispose();
    });
  });

  group('LivenessStrings', () {
    test('messageFor picks the success line per flow and copyWith merges reasons', () {
      const done = LivenessState(phase: LivenessPhase.success);
      expect(LivenessStrings.en.messageFor(done, FaceFlow.verify), 'Verified');
      expect(LivenessStrings.en.messageFor(done, FaceFlow.liveness), 'Live person confirmed');
      final custom = LivenessStrings.en.copyWith(success: 'Door open', reasons: {'NO_MATCH': 'Nope'});
      expect(custom.messageFor(done, FaceFlow.verify), 'Door open');
      expect(custom.reason('NO_MATCH'), 'Nope');
      expect(custom.reason('SPOOF'), LivenessStrings.en.reason('SPOOF'));
    });
  });
}
