import 'dart:async';
import 'dart:ui';

import 'package:lumiface/lumiface.dart';

class FakeSource implements FaceSignalSource, FrameCapturer, VideoRecorder {
  final ctrl = StreamController<FaceSignal>.broadcast(sync: true);
  int captures = 0;

  /// The recorder's state as the controller drove it: started, then stopped.
  bool recording = false;
  int recordings = 0;
  void Function(List<int> data, int tsMs)? _onChunk;

  @override
  Stream<FaceSignal> get signals => ctrl.stream;

  @override
  StreamFormat get format => StreamFormat.h264;

  @override
  Future<List<int>> captureJpeg() async {
    captures++;
    return [0xFF, 0xD8, captures];
  }

  @override
  void startRecording(void Function(List<int> data, int tsMs) onChunk) {
    recording = true;
    recordings++;
    _onChunk = onChunk;
  }

  @override
  void stopRecording() {
    recording = false;
    _onChunk = null;
  }

  /// A chunk the recorder cut at [tsMs]; delivered only while recording, like a real encoder.
  void chunk(int tsMs) => _onChunk?.call([0, 0, 0, 1, tsMs & 0xff], tsMs);

  void emit(FaceSignal s) => ctrl.add(s);
}

class FakeApi extends LumifaceClient {
  FakeApi(this.challenges, {this.response, this.flashColors = const [], this.oval}) : super(baseUrl: 'http://x');

  final List<Challenge> challenges;
  final List<Color> flashColors;
  final OvalTarget? oval;
  VerifyResult? response;
  String? planError;
  String? lastSubjectId;
  String? lastPurpose;
  LivenessConfig? sessionConfig;
  int enrollCalls = 0;

  /// What the controller streamed: chunk timestamps and events, in order, and the hello's format.
  final List<int> sentChunks = [];
  StreamFormat? format;
  final List<(StreamEventName, int, int?)> sentEvents = [];
  bool ended = false;
  bool closed = false;

  /// Stands in for the app's backend call; [subjectId] null = liveness session.
  Future<FaceSession> createSession({String? subjectId = 'E001', String purpose = ''}) async {
    lastSubjectId = subjectId;
    lastPurpose = purpose;
    return FaceSession(id: 's1', token: 'tok', mode: subjectId == null ? 'liveness' : 'verify', ttlSeconds: 60);
  }

  @override
  VerifyStream openStream(FaceSession session,
      {Map<String, dynamic> clientInfo = const {}, StreamFormat format = StreamFormat.jpeg}) {
    this.format = format;
    return _FakeStream(this);
  }

  /// The fake token names the subject, like the real one does server-side: `tok:<id>:<name>`.
  @override
  Future<Subject> enroll({required List<int> photoJpeg, required String enrolToken}) async {
    enrollCalls++;
    final parts = enrolToken.split(':');
    if (parts[1] == 'REJECT') throw LumifaceException('POSE_NOT_FRONTAL');
    return Subject(externalId: parts[1], name: parts.length > 2 ? parts[2] : '', enrollSpoofScore: 0.9);
  }
}

class _FakeStream implements VerifyStream {
  _FakeStream(this.api);
  final FakeApi api;

  @override
  Future<StreamPlan> get plan => api.planError != null
      ? Future.error(LumifaceException(api.planError!))
      : Future.value(StreamPlan(challenges: api.challenges, flashColors: api.flashColors, clientConfig: api.sessionConfig, oval: api.oval));

  @override
  void sendChunk(List<int> data, int tsMs) => api.sentChunks.add(tsMs);

  @override
  void event(StreamEventName name, int tsMs, {int? index}) => api.sentEvents.add((name, tsMs, index));

  @override
  Future<VerifyResult> end() async {
    api.ended = true;
    return api.response ?? const VerifyResult(ok: true, reasonCode: 'OK', verificationId: 1);
  }

  @override
  void close() => api.closed = true;
}

/// A well-framed face, [width] of the frame wide and centred; [yaw]/[pitch] as a detector with
/// angles (Apple Vision) would report them.
FaceSignal neutral(int ts, {double yaw = 0, double pitch = 0, double width = 0.45}) => FaceSignal(
      tsMs: ts,
      faceCount: 1,
      box: Rect.fromCenter(center: const Offset(0.5, 0.45), width: width, height: width * 1.125),
      yaw: yaw,
      pitch: pitch,
    );
