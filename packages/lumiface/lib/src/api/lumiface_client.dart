import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../liveness/signal_source.dart';
import '../models.dart';
import '_http.dart';

/// One verification in flight: video chunks go up as they are recorded, events tell the
/// server where to look, [end] resolves with the verdict. The server decodes the video into
/// frames and clocks everything itself.
abstract class VerifyStream {
  /// The server's plan, or a [LumifaceException] when it refused the session.
  Future<StreamPlan> get plan;

  /// Queues a chunk stamped with the device time of its first frame; chunks are dropped rather
  /// than buffered when the link is congested.
  void sendChunk(List<int> data, int tsMs);

  void event(StreamEventName name, int tsMs, {int? index});

  Future<VerifyResult> end();

  /// Abandons the stream; the server records the session as spent.
  void close();
}

/// The client an app ships with. It holds no secret: every call carries a
/// short-lived token that your backend obtained with the project key
/// (`POST /v1/sessions` → `session_token`, `POST /v1/subjects/tokens` → enrol
/// token). Everything the key can do — sessions, subjects, the audit log, the
/// policy — is plain REST for your backend; see `examples/backend`.
class LumifaceClient {
  LumifaceClient({required String baseUrl, Dio? dio})
    : _baseUrl = baseUrl.replaceFirst(RegExp(r'/$'), ''),
      _dio = dio ?? newDio(baseUrl);

  final String _baseUrl;
  final Dio _dio;

  /// Opens the session's stream. The server answers with the plan; the controller
  /// then sends chunks and events and finally [VerifyStream.end]s for the verdict.
  VerifyStream openStream(FaceSession session,
      {Map<String, dynamic> clientInfo = const {}, StreamFormat format = StreamFormat.jpeg}) {
    final url = Uri.parse('${_baseUrl.replaceFirst(RegExp(r'^http'), 'ws')}/v1/sessions/${session.id}/stream');
    return _SocketStream(WebSocketChannel.connect(url), session, clientInfo, format);
  }

  /// Enrols one photo as the subject named in [enrolToken].
  Future<Subject> enroll({required List<int> photoJpeg, required String enrolToken}) async {
    final form = FormData.fromMap({'photo': MultipartFile.fromBytes(photoJpeg, filename: 'photo.jpg')});
    final r = await _dio.post<Map<String, dynamic>>('/v1/subjects', data: form, options: bearer(enrolToken));
    if (r.statusCode == 201) return Subject.fromJson(r.data!);
    throwEnrolError(r);
  }
}

const _maxQueuedChunks = 8; // beyond this, drop chunks instead of adding latency

class _SocketStream implements VerifyStream {
  _SocketStream(this._channel, this._session, Map<String, dynamic> clientInfo, StreamFormat format) {
    _channel.ready.then(
      (_) {
        _open = true;
        _send(jsonEncode({'type': 'hello', 'token': _session.token, 'client': clientInfo, 'format': format.wire}));
      },
      onError: (Object e) => _settle(VerifyResult.clientError('NETWORK_ERROR', e.toString())),
    );
    _channel.stream.listen(
      _onMessage,
      onError: (Object e) {
        _settle(VerifyResult.clientError('NETWORK_ERROR', e.toString()));
      },
      onDone: () {
        _open = false;
        _settle(VerifyResult.clientError('NETWORK_ERROR', 'stream closed (${_channel.closeCode})'));
      },
    );
  }

  final WebSocketChannel _channel;
  final FaceSession _session;
  final _plan = Completer<StreamPlan>();
  final _result = Completer<VerifyResult>();
  bool _open = false;
  int _inFlight = 0;

  @override
  Future<StreamPlan> get plan => _plan.future;

  void _send(Object data) {
    if (_open) _channel.sink.add(data);
  }

  void _settle(VerifyResult r) {
    if (_result.isCompleted) return;
    final result = VerifyResult(
      ok: r.ok,
      reasonCode: r.reasonCode,
      mode: r.mode == 'verify' ? _session.mode : r.mode,
      scores: r.scores,
      verificationId: r.verificationId,
      sessionId: _session.id,
      subject: r.subject,
      message: r.message,
    );
    _result.complete(result);
    if (!_plan.isCompleted) _plan.completeError(LumifaceException(r.reasonCode, {'result': result}));
  }

  void _onMessage(dynamic data) {
    if (data is! String) return;
    final j = jsonDecode(data) as Map<String, dynamic>;
    switch (j['type']) {
      case 'plan':
        if (!_plan.isCompleted) _plan.complete(StreamPlan.fromJson(j));
      case 'result':
        _settle(VerifyResult.fromJson(j));
      case 'error':
        _settle(VerifyResult.clientError((j['reason_code'] as String?) ?? 'STREAM_ERROR'));
    }
  }

  @override
  void sendChunk(List<int> data, int tsMs) {
    if (!_open || _inFlight >= _maxQueuedChunks) return;
    final out = Uint8List(8 + data.length);
    // Big-endian 64-bit client time, written as two words: dart2js has no setUint64.
    final ms = tsMs < 0 ? 0 : tsMs;
    ByteData.view(out.buffer)
      ..setUint32(0, ms ~/ 0x100000000)
      ..setUint32(4, ms % 0x100000000);
    out.setRange(8, out.length, data);
    _inFlight++;
    _channel.sink.add(out);
    // The sink has no backpressure signal; count the chunk as delivered on the next turn.
    scheduleMicrotask(() => _inFlight--);
  }

  @override
  void event(StreamEventName name, int tsMs, {int? index}) {
    const wire = {
      StreamEventName.aligned: 'aligned',
      StreamEventName.challengeDone: 'challenge_done',
      StreamEventName.flash: 'flash',
      StreamEventName.flashEnd: 'flash_end',
    };
    _send(jsonEncode({'type': 'event', 'name': wire[name], 'ts': tsMs, 'index': ?index}));
  }

  @override
  Future<VerifyResult> end() {
    _send(jsonEncode({'type': 'end'}));
    return _result.future;
  }

  @override
  void close() {
    _settle(VerifyResult.clientError('CANCELLED'));
    _channel.sink.close();
  }
}
