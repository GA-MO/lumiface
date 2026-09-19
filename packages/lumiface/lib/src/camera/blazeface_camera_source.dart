import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

import '../liveness/signal_source.dart';
import '../models.dart';
import 'camera_source.dart';

CameraFaceSource createPlatformCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    BlazeFaceCameraSource(facing: facing);

const _glueAsset = 'packages/lumiface/assets/lumiface_blazeface.js';
const _modelAsset = 'packages/lumiface/assets/face_detection_short/model.json';
const _glueGlobal = 'lumifaceBlazeFace';

/// getUserMedia + TensorFlow.js BlazeFace for the signals, MediaRecorder for the stream the
/// server judges, for Flutter web.
///
/// The JS glue (`assets/lumiface_blazeface.js`, loaded from the package assets) imports
/// tfjs-core, the WASM and CPU backends and the converter from jsDelivr and loads the short-range
/// BlazeFace graph model from the package assets; pass [tfjsUrl], [wasmUrl] and [modelUrl] to
/// self-host. The largest box becomes the [FaceSignal]; BlazeFace reports no head angles.
class BlazeFaceCameraSource implements CameraFaceSource {
  BlazeFaceCameraSource({
    this.facing = CameraFacing.front,
    this.jpegQuality = 0.9,
    this.tfjsUrl,
    this.wasmUrl,
    this.modelUrl,
    this.backend = 'wasm',
    this.detectIntervalMs = 66,
    this.chunkMs = 250,
    this.videoBitsPerSecond = 1500000,
  });

  final CameraFacing facing;
  final double jpegQuality;
  final String? tfjsUrl;
  final String? wasmUrl;
  final String? modelUrl;

  /// "wasm" (the default) with the CPU backend as the fallback, or "cpu".
  final String backend;
  final int detectIntervalMs;

  /// MediaRecorder chunk length and target bit rate of the recording.
  final int chunkMs;
  final int videoBitsPerSecond;
  StreamFormat _format = StreamFormat.webm;

  final _signals = StreamController<FaceSignal>.broadcast();
  final String viewType = 'lumiface-video-${DateTime.now().microsecondsSinceEpoch}';
  late final web.HTMLVideoElement _video = web.HTMLVideoElement();
  web.MediaStream? _stream;
  JSObject? _detector;
  Timer? _timer;
  bool _initialized = false;
  bool _detecting = false;
  final Stopwatch _clock = Stopwatch()..start();

  @override
  Stream<FaceSignal> get signals => _signals.stream;

  @override
  bool get isInitialized => _initialized;

  @override
  bool get isMirrored => facing == CameraFacing.front;

  @override
  double get previewAspectRatio =>
      _video.videoHeight == 0 ? 1 : _video.videoWidth / _video.videoHeight;

  @override
  Future<void> initialize() async {
    _video
      ..autoplay = true
      ..muted = true
      ..setAttribute('playsinline', 'true')
      ..style.width = '100%'
      ..style.height = '100%'
      ..style.objectFit = 'cover';
    if (isMirrored) _video.style.transform = 'scaleX(-1)';
    ui_web.platformViewRegistry.registerViewFactory(viewType, (int _) => _video);
    final constraints = web.MediaStreamConstraints(
      audio: false.toJS,
      video: web.MediaTrackConstraints(
        facingMode: (facing == CameraFacing.front ? 'user' : 'environment').toJS,
        width: web.ConstrainULongRange(ideal: 1280),
        height: web.ConstrainULongRange(ideal: 720),
      ),
    );
    _stream = await web.window.navigator.mediaDevices.getUserMedia(constraints).toDart;
    _video.srcObject = _stream;
    await _video.play().toDart;
    await _loadGlue();
    final options = JSObject()
      ..['backend'] = backend.toJS
      ..['tfjsUrl'] = tfjsUrl?.toJS
      ..['wasmUrl'] = wasmUrl?.toJS
      ..['modelUrl'] = (modelUrl ?? ui_web.assetManager.getAssetUrl(_modelAsset)).toJS;
    final glue = web.window.getProperty<JSObject>(_glueGlobal.toJS);
    _detector = (await glue.callMethod<JSPromise<JSObject>>('create'.toJS, options).toDart);
    final rec = glue.callMethod<JSObject?>('recordingFormat'.toJS);
    if (rec == null) throw StateError('this browser cannot record video (MediaRecorder)');
    _format = StreamFormat.values.byName(rec.getProperty<JSString>('format'.toJS).toDart);
    _initialized = true;
  }

  @override
  StreamFormat get format => _format;

  @override
  void startRecording(void Function(List<int> data, int tsMs) onChunk) {
    final glue = web.window.getProperty<JSObject>(_glueGlobal.toJS);
    final now = (() => _clock.elapsedMilliseconds.toJS).toJS;
    final deliver = ((JSArrayBuffer buf, JSNumber ts) => onChunk(Uint8List.view(buf.toDart), ts.toDartInt)).toJS;
    glue.callMethodVarArgs('startRecording'.toJS, [_video, chunkMs.toJS, videoBitsPerSecond.toJS, now, deliver]);
  }

  @override
  void stopRecording() {
    web.window.getProperty<JSObject>(_glueGlobal.toJS).callMethod('stopRecording'.toJS);
  }

  Future<void> _loadGlue() async {
    if (web.window.has(_glueGlobal)) return;
    final script = web.HTMLScriptElement()
      ..type = 'module'
      ..src = ui_web.assetManager.getAssetUrl(_glueAsset);
    final loaded = Completer<void>();
    script.onload = ((web.Event _) => loaded.complete()).toJS;
    script.onerror = ((web.Event _) => loaded.completeError(StateError('cannot load $_glueAsset'))).toJS;
    web.document.head!.append(script);
    await loaded.future;
    while (!web.window.has(_glueGlobal)) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
  }

  @override
  Future<void> startStream() async {
    _timer ??= Timer.periodic(Duration(milliseconds: detectIntervalMs), (_) => _tick());
  }

  @override
  Future<void> stopStream() async {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _tick() async {
    if (_detecting || _detector == null || _signals.isClosed) return;
    _detecting = true;
    final ts = _clock.elapsedMilliseconds;
    try {
      final json = (await _detector!.callMethod<JSPromise<JSString>>('detect'.toJS, _video).toDart).toDart;
      if (!_signals.isClosed) _signals.add(_parse(json, ts));
    } catch (_) {
      if (!_signals.isClosed) _signals.add(FaceSignal.none(ts));
    } finally {
      _detecting = false;
    }
  }

  FaceSignal _parse(String json, int ts) {
    final faces = (jsonDecode(json) as Map<String, dynamic>)['faces'] as List;
    if (faces.isEmpty) return FaceSignal.none(ts);
    List<num>? best;
    for (final f in faces) {
      final box = ((f as Map<String, dynamic>)['box'] as List).cast<num>();
      if (best == null || box[2] * box[3] > best[2] * best[3]) best = box;
    }
    return FaceSignal(
      tsMs: ts,
      faceCount: faces.length,
      box: Rect.fromLTWH(best![0].toDouble(), best[1].toDouble(), best[2].toDouble(), best[3].toDouble()),
    );
  }

  @override
  Future<List<int>> captureJpeg() async {
    final glue = web.window.getProperty<JSObject>(_glueGlobal.toJS);
    final buffer = await glue
        .callMethod<JSPromise<JSArrayBuffer>>('captureJpeg'.toJS, _video, jpegQuality.toJS)
        .toDart;
    return Uint8List.view(buffer.toDart);
  }

  @override
  Future<void> setExposureLocked(bool locked) async {}

  @override
  Widget buildPreview(BuildContext context) => HtmlElementView(viewType: viewType);

  @override
  Future<void> dispose() async {
    await stopStream();
    stopRecording();
    await _signals.close();
    _detector?.callMethod('close'.toJS);
    _detector = null;
    final tracks = _stream?.getTracks().toDart ?? const [];
    for (final t in tracks) {
      t.stop();
    }
    _video.srcObject = null;
  }
}
