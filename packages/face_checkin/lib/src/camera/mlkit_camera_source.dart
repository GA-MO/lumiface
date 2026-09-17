import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

import '../models.dart';
import 'camera_source.dart';
import 'image_convert.dart';

/// Camera + ML Kit face detection for iOS/Android.
///
/// Produces [FaceSignal]s from the preview stream and can snapshot the latest
/// frame as an upright JPEG for upload.
class MlKitCameraSource implements CameraFaceSource {
  MlKitCameraSource({
    this.lensDirection = CameraLensDirection.front,
    this.resolution = ResolutionPreset.high,
    this.jpegQuality = 90,
  });

  final CameraLensDirection lensDirection;
  final ResolutionPreset resolution;
  final int jpegQuality;

  @override
  CameraController? controller;
  CameraDescription? _camera;
  late final FaceDetector _detector = FaceDetector(
    options: FaceDetectorOptions(
      enableClassification: true,
      enableTracking: true,
      performanceMode: FaceDetectorMode.fast,
      minFaceSize: 0.15,
    ),
  );

  final _signals = StreamController<FaceSignal>.broadcast();
  CameraImage? _latest;
  bool _detecting = false;
  bool _streaming = false;
  final Stopwatch _clock = Stopwatch()..start();

  @override
  Stream<FaceSignal> get signals => _signals.stream;

  @override
  bool get isInitialized => controller?.value.isInitialized ?? false;

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
    await _signals.close();
    await _detector.close();
    await controller?.dispose();
  }

  void _onImage(CameraImage image) {
    _latest = image;
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
    final rotation = InputImageRotationValue.fromRawValue(_rotationDegrees());
    final format = InputImageFormatValue.fromRawValue(image.format.raw);
    if (rotation == null || format == null || image.planes.length != 1) {
      _signals.add(FaceSignal.none(ts));
      return;
    }
    final plane = image.planes.first;
    final input = InputImage.fromBytes(
      bytes: plane.bytes,
      metadata: InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: rotation,
        format: format,
        bytesPerRow: plane.bytesPerRow,
      ),
    );
    List<Face> faces;
    try {
      faces = await _detector.processImage(input);
    } catch (_) {
      _signals.add(FaceSignal.none(ts));
      return;
    }
    if (_signals.isClosed) return;
    if (faces.isEmpty) {
      _signals.add(FaceSignal.none(ts));
      return;
    }
    faces.sort((a, b) => _area(b.boundingBox).compareTo(_area(a.boundingBox)));
    final f = faces.first;
    final rotated = rotation == InputImageRotation.rotation90deg || rotation == InputImageRotation.rotation270deg;
    // Bounding boxes come back in upright-image coordinates; the upright size
    // differs per platform for rotated frames (matches the ML Kit example painter).
    final double normW, normH;
    if (rotated) {
      normW = (Platform.isIOS ? image.width : image.height).toDouble();
      normH = (Platform.isIOS ? image.height : image.width).toDouble();
    } else {
      normW = image.width.toDouble();
      normH = image.height.toDouble();
    }
    final b = f.boundingBox;
    // ML Kit yaw (Euler Y) is positive when the face turns toward the image's
    // right. Front-camera frames are un-mirrored, so that equals the user's
    // own left; back camera is the opposite. FaceSignal wants +yaw == user's left.
    final yawSign = _camera!.lensDirection == CameraLensDirection.front ? 1.0 : -1.0;
    _signals.add(FaceSignal(
      tsMs: ts,
      faceCount: faces.length,
      box: Rect.fromLTWH(b.left / normW, b.top / normH, b.width / normW, b.height / normH),
      eyeOpenLeft: f.leftEyeOpenProbability,
      eyeOpenRight: f.rightEyeOpenProbability,
      smile: f.smilingProbability,
      yaw: f.headEulerAngleY == null ? null : f.headEulerAngleY! * yawSign,
      pitch: f.headEulerAngleX,
    ));
  }

  static double _area(Rect r) => r.width * r.height;

  @override
  Future<List<int>> captureJpeg() async {
    final image = _latest;
    if (image == null) throw StateError('no camera frame yet');
    final format = switch (image.format.group) {
      ImageFormatGroup.bgra8888 => 'bgra8888',
      ImageFormatGroup.nv21 => 'nv21',
      ImageFormatGroup.yuv420 => 'yuv420',
      _ => throw UnsupportedError('format ${image.format.group}'),
    };
    final raw = RawFrame(
      width: image.width,
      height: image.height,
      format: format,
      planes: [for (final p in image.planes) Uint8List.fromList(p.bytes)],
      bytesPerRow: [for (final p in image.planes) p.bytesPerRow],
      bytesPerPixel: [for (final p in image.planes) p.bytesPerPixel ?? 1],
      rotationDegrees: _rotationDegrees(),
    );
    return compute(_encode, (raw, jpegQuality));
  }

  static Uint8List _encode((RawFrame, int) args) => rawFrameToJpeg(args.$1, quality: args.$2);
}
