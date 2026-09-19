import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../liveness/signal_source.dart';
import '../models.dart';
import 'camera_source.dart';

CameraFaceSource createPlatformCameraFaceSource({CameraFacing facing = CameraFacing.front}) =>
    NativeCameraSource(lensDirection: facing == CameraFacing.front ? CameraLensDirection.front : CameraLensDirection.back);

/// Camera + the platform's own face detector and video encoder: TensorFlow Lite BlazeFace (short
/// range, bundled with the package) and MediaCodec H.264 on Android, Apple Vision
/// (`VNDetectFaceRectanglesRequest`) and VideoToolbox H.264 on iOS. Every frame goes to the plugin
/// over a method channel (`ai.lumiface/detector`) and comes back as upright, frame-normalised boxes
/// (Vision adds yaw and pitch, BlazeFace reports none) plus, while recording, the H.264 access
/// units the encoder has finished, each stamped with the frame time it was fed at.
///
/// Produces [FaceSignal]s from the preview stream and records it for the server.
class NativeCameraSource implements CameraFaceSource {
  NativeCameraSource({
    this.lensDirection = CameraLensDirection.front,
    this.resolution = ResolutionPreset.high,
  });

  static const channel = MethodChannel('ai.lumiface/detector');

  final CameraLensDirection lensDirection;
  final ResolutionPreset resolution;

  CameraController? controller;
  CameraDescription? _camera;

  final _signals = StreamController<FaceSignal>.broadcast();
  bool _detecting = false;
  bool _streaming = false;
  bool _recording = false;
  void Function(List<int> data, int tsMs)? _onChunk;
  final Stopwatch _clock = Stopwatch()..start();

  @override
  Stream<FaceSignal> get signals => _signals.stream;

  @override
  StreamFormat get format => StreamFormat.h264;

  @override
  void startRecording(void Function(List<int> data, int tsMs) onChunk) {
    _onChunk = onChunk;
    _recording = true;
  }

  @override
  void stopRecording() {
    if (!_recording) return;
    _recording = false;
    final deliver = _onChunk;
    _onChunk = null;
    channel.invokeMethod<List<Object?>>('stopRecording').then((chunks) {
      for (final c in (chunks ?? const []).cast<Map<Object?, Object?>>()) {
        deliver?.call(c['data'] as Uint8List, c['ts'] as int);
      }
    }).catchError((_) {});
  }

  @override
  bool get isInitialized => controller?.value.isInitialized ?? false;

  @override
  double get previewAspectRatio => isInitialized ? 1 / controller!.value.aspectRatio : 1;

  /// Whether frame coordinates need flipping to match the preview. camera_avfoundation already
  /// mirrors the front camera's frames, so on iOS they line up with the preview as they are.
  @override
  bool get isMirrored => lensDirection == CameraLensDirection.front && !Platform.isIOS;

  @override
  Future<void> setExposureLocked(bool locked) async {
    try {
      await controller?.setExposureMode(locked ? ExposureMode.locked : ExposureMode.auto);
    } catch (_) {}
  }

  @override
  Widget buildPreview(BuildContext context) => CameraPreview(controller!);

  @override
  Future<void> initialize() async {
    final cameras = await availableCameras();
    _camera = cameras.firstWhere((c) => c.lensDirection == lensDirection, orElse: () => cameras.first);
    controller = CameraController(
      _camera!,
      resolution,
      enableAudio: false,
      imageFormatGroup: Platform.isAndroid ? ImageFormatGroup.nv21 : ImageFormatGroup.bgra8888,
    );
    await controller!.initialize();
  }

  @override
  Future<void> startStream() async {
    if (_streaming || controller == null) return;
    _streaming = true;
    await controller!.startImageStream(_onImage);
  }

  @override
  Future<void> stopStream() async {
    if (!_streaming || controller == null) return;
    _streaming = false;
    await controller!.stopImageStream();
  }

  @override
  Future<void> dispose() async {
    await stopStream();
    stopRecording();
    await _signals.close();
    await controller?.dispose();
  }

  void _onImage(CameraImage image) {
    if (_detecting) return;
    _detecting = true;
    _detect(image).whenComplete(() => _detecting = false);
  }

  int _rotationDegrees() {
    final sensor = _camera!.sensorOrientation;
    if (Platform.isIOS) return sensor;
    final device = _deviceOrientationDegrees(controller!.value.deviceOrientation);
    return _camera!.lensDirection == CameraLensDirection.front
        ? (sensor + device) % 360
        : (sensor - device + 360) % 360;
  }

  static int _deviceOrientationDegrees(DeviceOrientation o) => switch (o) {
        DeviceOrientation.portraitUp => 0,
        DeviceOrientation.landscapeLeft => 90,
        DeviceOrientation.portraitDown => 180,
        DeviceOrientation.landscapeRight => 270,
      };

  Future<void> _detect(CameraImage image) async {
    final ts = _clock.elapsedMilliseconds;
    if (image.planes.length != 1) {
      _signals.add(FaceSignal.none(ts));
      return;
    }
    final plane = image.planes.first;
    Map<Object?, Object?> out;
    try {
      // camera_avfoundation delivers iOS frames already upright (and mirrored for the front camera);
      // Android delivers sensor orientation. The plugin makes both upright and un-mirrored.
      out = await channel.invokeMethod<Map<Object?, Object?>>('process', {
        'bytes': plane.bytes,
        'width': image.width,
        'height': image.height,
        'bytesPerRow': plane.bytesPerRow,
        'format': Platform.isAndroid ? 'nv21' : 'bgra8888',
        'rotation': Platform.isIOS ? 0 : _rotationDegrees(),
        'mirror': Platform.isIOS && _camera!.lensDirection == CameraLensDirection.front,
        'ts': ts,
        'record': _recording,
      }) ?? const {};
    } catch (_) {
      if (!_signals.isClosed) _signals.add(FaceSignal.none(ts));
      return;
    }
    if (_signals.isClosed) return;
    _signals.add(signalFromFaces((out['faces'] as List<Object?>?) ?? const [], ts));
    final deliver = _onChunk;
    if (deliver != null) {
      for (final c in ((out['chunks'] as List<Object?>?) ?? const []).cast<Map<Object?, Object?>>()) {
        deliver(c['data'] as Uint8List, c['ts'] as int);
      }
    }
  }

  /// The plugin's faces (`left, top, width, height` of the upright frame, `yaw`/`pitch` when it has
  /// them) as a signal: the largest box, angles from that face.
  @visibleForTesting
  static FaceSignal signalFromFaces(List<Object?> faces, int ts) {
    if (faces.isEmpty) return FaceSignal.none(ts);
    Map<Object?, Object?>? best;
    var bestArea = -1.0;
    for (final f in faces.cast<Map<Object?, Object?>>()) {
      final area = (f['width'] as num) * (f['height'] as num);
      if (area > bestArea) {
        bestArea = area.toDouble();
        best = f;
      }
    }
    return FaceSignal(
      tsMs: ts,
      faceCount: faces.length,
      box: Rect.fromLTWH((best!['left'] as num).toDouble(), (best['top'] as num).toDouble(),
          (best['width'] as num).toDouble(), (best['height'] as num).toDouble()),
      yaw: (best['yaw'] as num?)?.toDouble(),
      pitch: (best['pitch'] as num?)?.toDouble(),
    );
  }

}
