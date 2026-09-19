import 'dart:math' as math;

import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb;
import 'package:flutter/material.dart';

import '../api/lumiface_client.dart';
import '../camera/camera_factory.dart';
import '../camera/camera_source.dart';
import '../liveness/config.dart';
import '../liveness/face_verify_controller.dart';
import '../models.dart';
import 'strings.dart';
import 'theme.dart';

/// Everything a builder needs to draw one moment of a flow.
class FaceVerifyScope {
  const FaceVerifyScope({
    required this.controller,
    required this.state,
    required this.signal,
    required this.strings,
    required this.theme,
    required this.flow,
    required this.source,
  });

  final FaceFlowController controller;
  final LivenessState state;

  /// Latest raw face observation, for custom guides and debugging.
  final FaceSignal? signal;

  /// [FaceSignal.box] flipped to match a mirrored preview, for drawing.
  Rect? get displayBox {
    final b = signal?.box;
    if (b == null || !source.isMirrored) return b;
    return Rect.fromLTWH(1 - b.right, b.top, b.width, b.height);
  }

  final LivenessStrings strings;
  final FaceVerifyTheme theme;
  final FaceFlow flow;
  final CameraFaceSource source;

  String get message => strings.messageFor(state, flow);
  VerifyResult? get result => state.result;
  bool get isDone => state.isDone;

  void cancel() => controller.cancel();
}

typedef FaceScopeBuilder = Widget Function(BuildContext context, FaceVerifyScope scope);

/// Camera preview plus a flow ([FaceFlow.verify], [FaceFlow.liveness] or
/// [FaceFlow.enroll]) with a default overlay that every part can be replaced.
///
/// Minimal use: `FaceVerifyView(client: c, sessionProvider: () => myApi.faceSession(), onResult: ...)`.
/// Change colours and geometry with [theme], texts with [strings], single parts
/// of the overlay with [promptBuilder], [progressBuilder], [resultBuilder] and
/// [flashBuilder], or the whole overlay with [overlayBuilder]. Everything sits
/// on top of the camera; [FaceGuide] and [FaceDebugBar] are exported for reuse
/// inside custom overlays.
class FaceVerifyView extends StatefulWidget {
  const FaceVerifyView({
    super.key,
    required this.client,
    required this.onResult,
    this.flow = FaceFlow.verify,
    this.sessionProvider,
    this.enrolTokenProvider,
    this.config,
    this.strings = LivenessStrings.en,
    this.theme = const FaceVerifyTheme(),
    this.facing = CameraFacing.front,
    this.clientInfo = const {},
    this.showDebug = false,
    this.autoStart = true,
    this.sourceFactory,
    this.overlayBuilder,
    this.promptBuilder,
    this.progressBuilder,
    this.resultBuilder,
    this.flashBuilder,
    this.loadingBuilder,
    this.errorBuilder,
    this.onFlashChanged,
    this.onStateChanged,
    this.onController,
  });

  final LumifaceClient client;
  final void Function(VerifyResult result) onResult;

  /// [FaceFlow.verify] (default) or [FaceFlow.liveness] need [sessionProvider];
  /// [FaceFlow.enroll] needs [enrolTokenProvider]. The session the backend
  /// created decides between verify and liveness.
  final FaceFlow flow;

  /// Your backend creates the session with the project key (fixing the subject)
  /// and the app only holds its token. See [FaceVerifyController.sessionProvider].
  final Future<FaceSession> Function()? sessionProvider;

  /// For [FaceFlow.enroll]. See [FaceEnrollController.enrolTokenProvider].
  final Future<String> Function()? enrolTokenProvider;

  /// Overrides the project's `client_config`; null uses what the server sends.
  final LivenessConfig? config;
  final LivenessStrings strings;
  final FaceVerifyTheme theme;
  final CameraFacing facing;
  final Map<String, dynamic> clientInfo;
  final bool showDebug;
  final bool autoStart;

  /// Supplies your own camera/detector, e.g. a fake in widget tests.
  final CameraFaceSource Function()? sourceFactory;

  /// Replaces the whole default overlay. The camera preview stays underneath.
  final FaceScopeBuilder? overlayBuilder;
  final FaceScopeBuilder? promptBuilder;
  final FaceScopeBuilder? progressBuilder;
  final FaceScopeBuilder? resultBuilder;

  /// Draws the full-screen colour during the flash step. Must fill the screen
  /// with `scope.state.flashColor` for the server check to work.
  final FaceScopeBuilder? flashBuilder;
  final WidgetBuilder? loadingBuilder;
  final Widget Function(BuildContext context, Object error)? errorBuilder;

  /// Called with true when the screen-flash step starts and false when it ends.
  /// Push screen brightness to maximum here; the package adds no brightness plugin.
  final void Function(bool flashing)? onFlashChanged;
  final void Function(LivenessState state)? onStateChanged;

  /// Hands out the controller once the camera is ready (to call `start()` when
  /// [autoStart] is false, or `cancel()`).
  final void Function(FaceFlowController controller)? onController;

  @override
  State<FaceVerifyView> createState() => _FaceVerifyViewState();
}

class _FaceVerifyViewState extends State<FaceVerifyView> {
  CameraFaceSource? _source;
  FaceFlowController? _controller;
  Object? _error;
  FaceSignal? _lastSignal;
  bool _flashing = false;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  FaceFlowController _createController(CameraFaceSource source) {
    final platform = kIsWeb ? 'web' : defaultTargetPlatform.name;
    return switch (widget.flow) {
      FaceFlow.enroll => FaceEnrollController(
        source: source,
        capturer: source,
        client: widget.client,
        enrolTokenProvider:
            widget.enrolTokenProvider ?? (throw ArgumentError('FaceFlow.enroll needs enrolTokenProvider')),
        config: widget.config ?? const LivenessConfig(),
      ),
      FaceFlow.verify || FaceFlow.liveness => FaceVerifyController(
        source: source,
        recorder: source,
        client: widget.client,
        sessionProvider:
            widget.sessionProvider ?? (throw ArgumentError('FaceFlow.verify and liveness need sessionProvider')),
        flow: widget.flow,
        config: widget.config,
        clientInfo: {'platform': platform, 'sdk': 'lumiface-flutter', ...widget.clientInfo},
      ),
    };
  }

  Future<void> _boot() async {
    try {
      final source = widget.sourceFactory?.call() ?? createCameraFaceSource(facing: widget.facing);
      await source.initialize();
      final controller = _createController(source);
      controller.state.addListener(_onState);
      source.signals.listen((s) {
        _lastSignal = s;
        if (widget.showDebug && mounted) setState(() {});
      });
      if (!mounted) {
        controller.dispose();
        await source.dispose();
        return;
      }
      setState(() {
        _source = source;
        _controller = controller;
      });
      await source.startStream();
      widget.onController?.call(controller);
      if (widget.autoStart) await controller.start();
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  void _onState() {
    final st = _controller!.state.value;
    widget.onStateChanged?.call(st);
    if (st.isDone) {
      _source?.stopStream();
      widget.onResult(st.result!);
    }
    final flashing = st.phase == LivenessPhase.flash;
    if (flashing != _flashing) {
      _flashing = flashing;
      _source?.setExposureLocked(flashing);
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
    final theme = widget.theme;
    if (_error != null) {
      return widget.errorBuilder?.call(context, _error!) ??
          ColoredBox(
            color: theme.backgroundColor,
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '${widget.strings.cameraError}\n$_error',
                  textAlign: TextAlign.center,
                  style: theme.messageStyle.copyWith(fontSize: 16),
                ),
              ),
            ),
          );
    }
    final source = _source;
    final controller = _controller;
    if (source == null || controller == null || !source.isInitialized) {
      return widget.loadingBuilder?.call(context) ??
          ColoredBox(
            color: theme.backgroundColor,
            child: Center(child: Text(widget.strings.starting, style: theme.messageStyle)),
          );
    }
    final scope = FaceVerifyScope(
      controller: controller,
      state: controller.state.value,
      signal: _lastSignal,
      strings: widget.strings,
      theme: theme,
      flow: controller.flow,
      source: source,
    );
    return ColoredBox(
      color: theme.backgroundColor,
      child: LayoutBuilder(
        builder: (context, constraints) {
          // FaceCameraPreview fits the frame by width and crops top/bottom; a frame shorter than
          // the box is letterboxed, so only the vertical crop can hide part of the face.
          final aspect = source.previewAspectRatio;
          final frameH = constraints.maxWidth / aspect;
          controller.visibleRegion = frameH > constraints.maxHeight
              ? visibleRegionFor(aspect, constraints.maxWidth / constraints.maxHeight)
              : fullFrame;
          controller.frameAspect = aspect;
          return Stack(
            fit: StackFit.expand,
            children: [
              FaceCameraPreview(source: source),
              if (widget.overlayBuilder != null)
                widget.overlayBuilder!(context, scope)
              else
                FaceVerifyOverlay(
                  scope: scope,
                  showDebug: widget.showDebug,
                  promptBuilder: widget.promptBuilder,
                  progressBuilder: widget.progressBuilder,
                  resultBuilder: widget.resultBuilder,
                ),
              if (scope.state.isFlashing)
                widget.flashBuilder?.call(context, scope) ?? ColoredBox(color: scope.state.flashColor!),
            ],
          );
        },
      ),
    );
  }
}

/// Fills its box with the camera, cropped like `BoxFit.cover`.
class FaceCameraPreview extends StatelessWidget {
  const FaceCameraPreview({super.key, required this.source});
  final CameraFaceSource source;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final w = constraints.maxWidth;
      final h = w / source.previewAspectRatio;
      return ClipRect(
        child: OverflowBox(
          maxWidth: double.infinity,
          maxHeight: double.infinity,
          child: SizedBox(
            width: w,
            height: h,
            child: FittedBox(
              fit: BoxFit.cover,
              child: SizedBox(width: w, height: h, child: source.buildPreview(context)),
            ),
          ),
        ),
      );
    },
  );
}

/// The default overlay: guide mask, progress bar, prompt, result buttons.
class FaceVerifyOverlay extends StatelessWidget {
  const FaceVerifyOverlay({
    super.key,
    required this.scope,
    this.showDebug = false,
    this.promptBuilder,
    this.progressBuilder,
    this.resultBuilder,
  });

  final FaceVerifyScope scope;
  final bool showDebug;
  final FaceScopeBuilder? promptBuilder;
  final FaceScopeBuilder? progressBuilder;
  final FaceScopeBuilder? resultBuilder;

  @override
  Widget build(BuildContext context) {
    final st = scope.state;
    final t = scope.theme;
    return Stack(
      fit: StackFit.expand,
      children: [
        FaceGuide(theme: t, phase: st.phase, box: showDebug ? scope.displayBox : null, target: st.target),
        SafeArea(
          child: Column(
            children: [
              const SizedBox(height: 16),
              if (progressBuilder != null)
                progressBuilder!(context, scope)
              else if (t.showProgress && st.challengeCount > 0)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: LinearProgressIndicator(
                    value: st.progress,
                    backgroundColor: t.progressBackgroundColor,
                    color: t.progressColor,
                  ),
                ),
              const Spacer(),
              if (promptBuilder != null)
                promptBuilder!(context, scope)
              else
                Padding(
                  padding: t.messagePadding,
                  child: Text(scope.message, textAlign: TextAlign.center, style: t.messageStyle),
                ),
              if (st.isDone)
                if (resultBuilder != null)
                  resultBuilder!(context, scope)
                else if (t.showButtons)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 24),
                    child: FilledButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      child: Text(st.phase == LivenessPhase.success ? scope.strings.done : scope.strings.retry),
                    ),
                  ),
              if (showDebug && scope.signal != null) FaceDebugBar(signal: scope.signal!),
            ],
          ),
        ),
      ],
    );
  }
}

/// Dimmed mask with a face-shaped cut-out whose colour follows the phase.
class FaceGuide extends StatelessWidget {
  const FaceGuide({super.key, required this.theme, required this.phase, this.box, this.target});
  final FaceVerifyTheme theme;
  final LivenessPhase phase;
  final Rect? box;

  /// The server's oval for a face_move challenge, as fractions of this widget; overrides the theme's shape.
  final Rect? target;

  Color get color => switch (phase) {
    LivenessPhase.success => theme.guideSuccessColor,
    LivenessPhase.failed => theme.guideFailedColor,
    LivenessPhase.challenge => theme.guideActiveColor,
    _ => theme.guideColor,
  };

  @override
  Widget build(BuildContext context) => CustomPaint(
    painter: FaceGuidePainter(theme: theme, color: color, box: box, target: target),
  );
}

/// The guide at `guideWidthFraction`, shrunk to fit [size] and kept clear of a band at the
/// bottom where the prompt and the buttons live, so neither ever sits on the guide's edge.
Rect guideRect(FaceVerifyTheme theme, Size size) {
  final margin = math.min(size.width, size.height) * 0.06;
  final bottomBand = (size.height * 0.2).clamp(72.0, 140.0);
  var w = size.width * theme.guideWidthFraction;
  var h = w * theme.guideAspectRatio;
  final maxH = math.max(0.0, size.height - margin - bottomBand);
  if (h > maxH) {
    h = maxH;
    w = h / theme.guideAspectRatio;
  }
  final top = (size.height * theme.guideCenterY - h / 2)
      .clamp(margin, math.max(margin, size.height - h - bottomBand))
      .toDouble();
  return Rect.fromLTWH((size.width - w) / 2, top, w, h);
}

class FaceGuidePainter extends CustomPainter {
  FaceGuidePainter({required this.theme, required this.color, this.box, this.target});
  final FaceVerifyTheme theme;
  final Color color;
  final Rect? box;
  final Rect? target;

  @override
  void paint(Canvas canvas, Size size) {
    if (theme.guideShape != FaceGuideShape.none) {
      final t = target;
      final rect = t == null
          ? guideRect(theme, size)
          : Rect.fromLTWH(t.left * size.width, t.top * size.height, t.width * size.width, t.height * size.height);
      final cutout = Path();
      if (theme.guideShape == FaceGuideShape.oval) {
        cutout.addOval(rect);
      } else {
        cutout.addRRect(RRect.fromRectAndRadius(rect, Radius.circular(rect.width * 0.2)));
      }
      final mask = Path()
        ..addRect(Offset.zero & size)
        ..addPath(cutout, Offset.zero)
        ..fillType = PathFillType.evenOdd;
      canvas.drawPath(mask, Paint()..color = theme.maskColor);
      canvas.drawPath(
        cutout,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = theme.guideStrokeWidth,
      );
    }
    if (box != null) {
      final b = box!;
      canvas.drawRect(
        Rect.fromLTWH(b.left * size.width, b.top * size.height, b.width * size.width, b.height * size.height),
        Paint()
          ..color = theme.debugBoxColor
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2,
      );
    }
  }

  @override
  bool shouldRepaint(FaceGuidePainter old) =>
      old.color != color || old.box != box || old.theme != theme || old.target != target;
}

/// One line of raw detector values, for calibration sessions.
class FaceDebugBar extends StatelessWidget {
  const FaceDebugBar({super.key, required this.signal});
  final FaceSignal signal;

  String _f(double? v) => v == null
      ? '-'
      : (v * 100).round() / 100 == v
      ? v.toStringAsFixed(2)
      : v.toStringAsFixed(1);

  @override
  Widget build(BuildContext context) => Container(
    color: Colors.black54,
    padding: const EdgeInsets.all(8),
    child: Text(
      'faces=${signal.faceCount} w=${_f(signal.box?.width)} h=${_f(signal.box?.height)} '
      'yaw=${_f(signal.yaw)} pitch=${_f(signal.pitch)} '
      'cx=${_f(signal.box?.center.dx)} cy=${_f(signal.box?.center.dy)} '
      'min(w,h)=${signal.box == null ? '-' : math.min(signal.box!.width, signal.box!.height).toStringAsFixed(2)}',
      style: const TextStyle(color: Colors.white, fontSize: 11, fontFamily: 'monospace'),
    ),
  );
}
