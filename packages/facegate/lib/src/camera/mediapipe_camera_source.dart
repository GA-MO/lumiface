import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

import '../models.dart';
import 'camera_source.dart';

CameraFaceSource createPlatformCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    MediaPipeCameraSource(facing: facing);

const _glueAsset = 'packages/facegate/assets/facegate_mediapipe.js';
const _glueGlobal = 'facegateMediaPipe';

/// getUserMedia + MediaPipe FaceLandmarker for Flutter web.
///
/// The JS glue (`assets/facegate_mediapipe.js`, loaded from the package assets)
/// imports `@mediapipe/tasks-vision` from jsDelivr and the face_landmarker
/// model from Google's CDN; pass [tasksVisionUrl] and [modelUrl] to self-host.
/// Blendshapes give eye-open and smile probabilities, the facial transformation
/// matrix gives yaw/pitch, nose tip and eye centres give the parallax.
class MediaPipeCameraSource implements CameraFaceSource {
  MediaPipeCameraSource({
    this.facing = CameraFacing.front,
    this.jpegQuality = 0.9,
    this.tasksVisionUrl,
    this.modelUrl,
    this.delegate = 'GPU',
    this.yawSign = 1,
    this.detectIntervalMs = 66,
  });

  final CameraFacing facing;
  final double jpegQuality;
  final String? tasksVisionUrl;
  final String? modelUrl;
  final String delegate;

  /// Flip to -1 if a head turn to the user's left reports negative yaw.
  final double yawSign;
  final int detectIntervalMs;

  final _signals = StreamController<FaceSignal>.broadcast();
  final String viewType = 'facegate-video-${DateTime.now().microsecondsSinceEpoch}';
  late final web.HTMLVideoElement _video = web.HTMLVideoElement();
  web.MediaStream? _stream;
  JSObject? _landmarker;
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
      ..['delegate'] = delegate.toJS
      ..['tasksVisionUrl'] = tasksVisionUrl?.toJS
      ..['modelUrl'] = modelUrl?.toJS;
    final glue = web.window.getProperty<JSObject>(_glueGlobal.toJS);
    _landmarker = (await glue.callMethod<JSPromise<JSObject>>('create'.toJS, options).toDart);
    _initialized = true;
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

  void _tick() {
    if (_detecting || _landmarker == null || _signals.isClosed) return;
    _detecting = true;
    try {
      final ts = _clock.elapsedMilliseconds;
      final json = _landmarker!.callMethod<JSString>('detect'.toJS, _video, ts.toJS).toDart;
      _signals.add(_parse(json, ts));
    } catch (_) {
      _signals.add(FaceSignal.none(_clock.elapsedMilliseconds));
    } finally {
      _detecting = false;
    }
  }

  FaceSignal _parse(String json, int ts) {
    final faces = (jsonDecode(json) as Map<String, dynamic>)['faces'] as List;
    if (faces.isEmpty) return FaceSignal.none(ts);
    final f = faces.first as Map<String, dynamic>;
    final box = (f['box'] as List).cast<num>();
    Offset? point(String key) {
      final p = (f[key] as List?)?.cast<num>();
      return p == null ? null : Offset(p[0].toDouble(), p[1].toDouble());
    }
    final yaw = (f['yaw'] as num?)?.toDouble();
    return FaceSignal(
      tsMs: ts,
      faceCount: faces.length,
      box: Rect.fromLTWH(box[0].toDouble(), box[1].toDouble(), box[2].toDouble(), box[3].toDouble()),
      eyeOpenLeft: (f['eyeOpenLeft'] as num?)?.toDouble(),
      eyeOpenRight: (f['eyeOpenRight'] as num?)?.toDouble(),
      smile: (f['smile'] as num?)?.toDouble(),
      yaw: yaw == null ? null : yaw * yawSign,
      pitch: (f['pitch'] as num?)?.toDouble(),
      nose: point('nose'),
      leftEye: point('leftEye'),
      rightEye: point('rightEye'),
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
    await _signals.close();
    _landmarker?.callMethod('close'.toJS);
    _landmarker = null;
    final tracks = _stream?.getTracks().toDart ?? const [];
    for (final t in tracks) {
      t.stop();
    }
    _video.srcObject = null;
  }
}
