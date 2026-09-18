import 'package:flutter/widgets.dart';

import '../liveness/signal_source.dart';

/// Camera-backed signal source + frame capturer used by [FaceVerifyView].
/// Implementations: ML Kit on iOS/Android, MediaPipe on the web.
abstract class CameraFaceSource implements FaceSignalSource, FrameCapturer {
  bool get isInitialized;

  /// Camera frame aspect ratio (width / height of the upright preview), 1 until initialised.
  double get previewAspectRatio;

  /// True when the preview shows the user mirrored (front cameras).
  bool get isMirrored;

  Future<void> initialize();
  Future<void> startStream();
  Future<void> stopStream();

  /// Freeze auto-exposure while the screen flashes so the tint stays measurable.
  Future<void> setExposureLocked(bool locked);

  Widget buildPreview(BuildContext context);
  Future<void> dispose();
}

enum CameraFacing { front, back }
