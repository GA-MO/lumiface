import 'package:lumiface/lumiface.dart';
import 'package:flutter/material.dart';

import '../brightness.dart';
import '../main.dart';

/// Everything on top of the camera is drawn here; the package only supplies
/// the preview, the state machine and the flash colour.
class CustomUiPage extends StatelessWidget {
  const CustomUiPage({super.key, required this.settings, required this.onResult});
  final AppSettings settings;
  final void Function(VerifyResult) onResult;

  @override
  Widget build(BuildContext context) => FaceVerifyView(
        client: settings.client,
        subjectId: settings.subjectId.isEmpty ? null : settings.subjectId,
        purpose: 'custom',
        strings: settings.strings,
        onResult: onResult,
        onFlashChanged: setMaxBrightness,
        overlayBuilder: (context, scope) => _Overlay(scope: scope),
      );
}

class _Overlay extends StatelessWidget {
  const _Overlay({required this.scope});
  final FaceVerifyScope scope;

  @override
  Widget build(BuildContext context) {
    final st = scope.state;
    final box = scope.displayBox;
    final accent = switch (st.phase) {
      LivenessPhase.success => Colors.greenAccent,
      LivenessPhase.failed => Colors.redAccent,
      LivenessPhase.challenge => Colors.orangeAccent,
      _ => Colors.white70,
    };
    return Stack(
      fit: StackFit.expand,
      children: [
        if (box != null && !st.isDone)
          LayoutBuilder(
            builder: (context, c) => Stack(children: [
              Positioned(
                left: box.left * c.maxWidth,
                top: box.top * c.maxHeight,
                width: box.width * c.maxWidth,
                height: box.height * c.maxHeight,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    border: Border.all(color: accent, width: 3),
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
            ]),
          ),
        SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () {
                        scope.cancel();
                        Navigator.of(context).maybePop();
                      },
                      icon: const Icon(Icons.close, color: Colors.white),
                    ),
                    const Spacer(),
                    for (var i = 0; i < st.challengeCount; i++)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 3),
                        child: Icon(
                          i < st.challengeIndex || st.isDone ? Icons.check_circle : Icons.circle_outlined,
                          color: accent,
                          size: 18,
                        ),
                      ),
                  ],
                ),
              ),
              const Spacer(),
              Container(
                margin: const EdgeInsets.all(24),
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(color: Colors.black87, borderRadius: BorderRadius.circular(20)),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(scope.message,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: accent, fontSize: 20, fontWeight: FontWeight.bold)),
                    if (st.isDone) ...[
                      const SizedBox(height: 8),
                      Text(
                        'match ${fmt(scope.result?.scores.match)} · spoof ${fmt(scope.result?.scores.spoof)}',
                        style: const TextStyle(color: Colors.white70),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton(
                        onPressed: () => Navigator.of(context).maybePop(),
                        child: Text(st.phase == LivenessPhase.success ? scope.strings.done : scope.strings.retry),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
