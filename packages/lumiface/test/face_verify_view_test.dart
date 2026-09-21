import 'dart:async';

import 'package:lumiface/lumiface.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

class FakeCamera extends FakeSource implements CameraFaceSource {
  bool initialized = false;
  bool streaming = false;
  bool disposed = false;
  final exposure = <bool>[];

  @override
  bool get isInitialized => initialized;
  @override
  double get previewAspectRatio => 0.75;
  @override
  bool get isMirrored => true;
  @override
  Future<void> initialize() async => initialized = true;
  @override
  Future<void> startStream() async => streaming = true;
  @override
  Future<void> stopStream() async => streaming = false;
  @override
  Future<void> setExposureLocked(bool locked) async => exposure.add(locked);
  @override
  Widget buildPreview(BuildContext context) => const ColoredBox(color: Colors.grey, key: Key('preview'));
  @override
  Future<void> dispose() async => disposed = true;
}

void main() {
  late FakeCamera cam;
  late FakeApi api;

  setUp(() {
    cam = FakeCamera();
    api = FakeApi([Challenge.faceMove], flashColors: const [Color(0xFFFF0000)]);
  });

  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump();
    await tester.pump();
  }

  Future<void> emit(WidgetTester tester, FaceSignal s) async {
    cam.emit(s);
    await settle(tester);
  }

  Widget app(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('default overlay shows hints, prompts and the done button', (tester) async {
    final results = <VerifyResult>[];
    await tester.pumpWidget(app(FaceVerifyView(
      client: api,
      sessionProvider: api.createSession,
      sourceFactory: () => cam,
      onResult: results.add,
    )));
    await settle(tester);
    expect(find.byKey(const Key('preview')), findsOneWidget);
    expect(cam.streaming, true);
    expect(find.text('Position your face in the frame'), findsOneWidget);

    await emit(tester, neutral(0, width: 0.6));
    expect(find.text('Move back a little'), findsOneWidget);
    await emit(tester, neutral(100));
    expect(find.text('Hold still…'), findsOneWidget);
    await emit(tester, neutral(800));
    expect(find.text('Move closer until your face fills the oval'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    await emit(tester, neutral(900, width: 0.3));
    expect(find.text('Move closer until your face fills the oval'), findsOneWidget);
    await emit(tester, neutral(1200, width: 0.6));
    await emit(tester, neutral(1800, width: 0.6));
    await emit(tester, neutral(2300, width: 0.6));
    expect(find.text('Hold still…'), findsOneWidget);
    expect(cam.exposure, [true]);
    await emit(tester, neutral(2900));
    await emit(tester, neutral(3800));
    await settle(tester);
    expect(find.text('Verified'), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);
    expect(results.single.ok, true);
    expect(cam.streaming, false);
    expect(cam.exposure, [true, false]);
  });

  testWidgets('builders replace parts of the overlay and see the scope', (tester) async {
    LivenessState? seen;
    await tester.pumpWidget(app(FaceVerifyView(
      client: api,
      sessionProvider: () => api.createSession(reference: false),
      sourceFactory: () => cam,
      strings: LivenessStrings.th,
      theme: const FaceVerifyTheme(guideShape: FaceGuideShape.none, showProgress: false),
      promptBuilder: (context, scope) => Text('custom:${scope.message}:${scope.flow.name}'),
      progressBuilder: (context, scope) => Text('progress:${scope.state.challengeCount}'),
      onStateChanged: (s) => seen = s,
      onResult: (_) {},
    )));
    await settle(tester);
    expect(find.text('custom:วางใบหน้าให้อยู่ในกรอบ:liveness'), findsOneWidget);
    expect(find.text('progress:1'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    expect(seen!.phase, LivenessPhase.aligning);
  });

  testWidgets('overlayBuilder replaces everything, autoStart false hands out the controller', (tester) async {
    FaceVerifyController? ctrl;
    await tester.pumpWidget(app(FaceVerifyView(
      client: api,
      sessionProvider: api.createSession,
      sourceFactory: () => cam,
      autoStart: false,
      onController: (c) => ctrl = c,
      overlayBuilder: (context, scope) => Center(child: Text('phase:${scope.state.phase.name}')),
      onResult: (_) {},
    )));
    await settle(tester);
    expect(find.text('phase:idle'), findsOneWidget);
    expect(find.byType(FaceGuide), findsNothing);
    unawaited(ctrl!.start());
    await settle(tester);
    expect(find.text('phase:aligning'), findsOneWidget);
  });

  testWidgets('camera failure renders the error builder', (tester) async {
    await tester.pumpWidget(app(FaceVerifyView(
      client: api,
      sessionProvider: api.createSession,
      sourceFactory: () => throw StateError('no camera'),
      errorBuilder: (context, e) => Text('err:$e'),
      onResult: (_) {},
    )));
    await settle(tester);
    expect(find.text('err:Bad state: no camera'), findsOneWidget);
  });
}
