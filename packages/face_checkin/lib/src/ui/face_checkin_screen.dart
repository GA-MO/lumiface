import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart' show defaultTargetPlatform;
import 'package:flutter/material.dart';

import '../api/checkin_api.dart';
import '../camera/camera_source_stub.dart' if (dart.library.io) '../camera/mlkit_camera_source.dart';
import '../liveness/config.dart';
import '../liveness/liveness_controller.dart';
import '../camera/camera_source.dart';
import '../models.dart';
import 'strings.dart';

/// Drop-in check-in screen: camera preview, oval guide, challenge prompts,
/// result. Calls [onResult] once with the outcome.
class FaceCheckinScreen extends StatefulWidget {
  const FaceCheckinScreen({
    super.key,
    required this.api,
    required this.employeeId,
    required this.onResult,
    this.config = const LivenessConfig(),
    this.strings = LivenessStrings.en,
    this.lensDirection = CameraLensDirection.front,
    this.clientInfo = const {},
    this.showDebug = false,
    this.onFlashChanged,
  });

  final CheckinApi api;
  final String employeeId;
  final void Function(CheckinResult result) onResult;
  final LivenessConfig config;
  final LivenessStrings strings;
  final CameraLensDirection lensDirection;
  final Map<String, dynamic> clientInfo;
  final bool showDebug;

  /// Called with true when the screen-flash step starts and false when it ends.
  /// Use it to push screen brightness to maximum so the face reflects more light
  /// (the package adds no brightness plugin itself).
  final void Function(bool flashing)? onFlashChanged;

  @override
  State<FaceCheckinScreen> createState() => _FaceCheckinScreenState();
}

class _FaceCheckinScreenState extends State<FaceCheckinScreen> {
  CameraFaceSource? _source;
  LivenessController? _controller;
  String? _error;
  FaceSignal? _lastSignal;
  bool _exposureLocked = false;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    final platform = defaultTargetPlatform.name;
    try {
      final CameraFaceSource source = MlKitCameraSource(lensDirection: widget.lensDirection);
      await source.initialize();
      final controller = LivenessController(
        source: source,
        capturer: source,
        api: widget.api,
        employeeId: widget.employeeId,
        config: widget.config,
        clientInfo: {'platform': platform, ...widget.clientInfo},
      );
      controller.state.addListener(_onState);
      if (widget.showDebug) {
        source.signals.listen((s) {
          if (mounted) setState(() => _lastSignal = s);
        });
      }
      setState(() {
        _source = source;
        _controller = controller;
      });
      await source.startStream();
      await controller.start();
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  void _onState() {
    final st = _controller!.state.value;
    if (st.isDone) {
      _source?.stopStream();
      widget.onResult(st.result!);
    }
    // Auto-exposure would cancel the tint we are trying to measure.
    final flashing = st.phase == LivenessPhase.flash;
    if (flashing != _exposureLocked) {
      _exposureLocked = flashing;
      _source?.controller
          ?.setExposureMode(flashing ? ExposureMode.locked : ExposureMode.auto)
          .catchError((Object _) {});
      widget.onFlashChanged?.call(flashing);
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _controller?.state.removeListener(_onState);
    _controller?.dispose();
    _source?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.strings;
    if (_error != null) {
      return Scaffold(body: Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_error!))));
    }
    final source = _source;
    final controller = _controller;
    if (source == null || controller == null || !source.isInitialized) {
      return Scaffold(body: Center(child: Text(s.starting)));
    }
    final st = controller.state.value;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          _Preview(controller: source.controller!),
          CustomPaint(painter: _OvalMaskPainter(
            color: switch (st.phase) {
              LivenessPhase.success => Colors.green,
              LivenessPhase.failed => Colors.red,
              LivenessPhase.challenge => Colors.amber,
              _ => Colors.white,
            },
            box: widget.showDebug ? _lastSignal?.box : null,
          )),
          if (st.phase == LivenessPhase.flash && st.flashColor != null) ColoredBox(color: st.flashColor!),
          SafeArea(
            child: Column(
              children: [
                const SizedBox(height: 16),
                if (st.challengeCount > 0)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: LinearProgressIndicator(
                      value: switch (st.phase) {
                        LivenessPhase.aligning => 0,
                        LivenessPhase.challenge => (st.challengeIndex + 0.5) / (st.challengeCount + 1),
                        LivenessPhase.flash || LivenessPhase.uploading => st.challengeCount / (st.challengeCount + 1),
                        LivenessPhase.success => 1,
                        _ => null,
                      },
                      backgroundColor: Colors.white24,
                      color: Colors.white,
                    ),
                  ),
                const Spacer(),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
                  child: Text(
                    _message(st, s),
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
                  ),
                ),
                if (st.phase == LivenessPhase.failed)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 24),
                    child: FilledButton(onPressed: () => Navigator.of(context).maybePop(), child: Text(s.retry)),
                  ),
                if (st.phase == LivenessPhase.success)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 24),
                    child: FilledButton(onPressed: () => Navigator.of(context).maybePop(), child: Text(s.done)),
                  ),
                if (widget.showDebug && _lastSignal != null) _DebugBar(signal: _lastSignal!),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _message(LivenessState st, LivenessStrings s) => switch (st.phase) {
        LivenessPhase.idle || LivenessPhase.starting => s.starting,
        LivenessPhase.aligning => s.hints[st.hint ?? AlignHint.noFace] ?? '',
        LivenessPhase.challenge =>
          st.hint != null ? (s.hints[st.hint!] ?? '') : (s.challenges[st.challenge!] ?? st.challenge!.wire),
        LivenessPhase.flash => s.flashing,
        LivenessPhase.uploading => s.uploading,
        LivenessPhase.success => s.success,
        LivenessPhase.failed => s.reason(st.result?.reasonCode ?? ''),
      };
}

class _Preview extends StatelessWidget {
  const _Preview({required this.controller});
  final CameraController controller;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final previewAspect = controller.value.aspectRatio; // width / height in landscape sensor terms
    return ClipRect(
      child: OverflowBox(
        maxWidth: double.infinity,
        maxHeight: double.infinity,
        child: SizedBox(
          width: size.width,
          height: size.width * previewAspect,
          child: FittedBox(
            fit: BoxFit.cover,
            child: SizedBox(width: size.width, height: size.width * previewAspect, child: CameraPreview(controller)),
          ),
        ),
      ),
    );
  }
}

class _OvalMaskPainter extends CustomPainter {
  _OvalMaskPainter({required this.color, this.box});
  final Color color;
  final Rect? box;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width * 0.72;
    final h = w * 1.35;
    final oval = Rect.fromCenter(center: Offset(size.width / 2, size.height * 0.42), width: w, height: h);
    final mask = Path()
      ..addRect(Offset.zero & size)
      ..addOval(oval)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(mask, Paint()..color = Colors.black.withValues(alpha: 0.55));
    canvas.drawOval(oval, Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4);
    if (box != null) {
      final b = box!;
      canvas.drawRect(
        Rect.fromLTWH(b.left * size.width, b.top * size.height, b.width * size.width, b.height * size.height),
        Paint()
          ..color = Colors.cyan
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2,
      );
    }
  }

  @override
  bool shouldRepaint(_OvalMaskPainter old) => old.color != color || old.box != box;
}

class _DebugBar extends StatelessWidget {
  const _DebugBar({required this.signal});
  final FaceSignal signal;

  String _f(double? v) => v == null ? '-' : (v * 100).round() / 100 == v ? v.toStringAsFixed(2) : v.toStringAsFixed(1);

  @override
  Widget build(BuildContext context) => Container(
        color: Colors.black54,
        padding: const EdgeInsets.all(8),
        child: Text(
          'faces=${signal.faceCount} w=${_f(signal.box?.width)} eye=${_f(signal.eyeOpen)} '
          'smile=${_f(signal.smile)} yaw=${_f(signal.yaw)} pitch=${_f(signal.pitch)} px=${_f(signal.noseParallax)} '
          'cx=${_f(signal.box?.center.dx)} cy=${_f(signal.box?.center.dy)} '
          'min(w,h)=${signal.box == null ? '-' : math.min(signal.box!.width, signal.box!.height).toStringAsFixed(2)}',
          style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace'),
        ),
      );
}
