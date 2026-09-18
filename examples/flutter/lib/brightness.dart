import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:screen_brightness/screen_brightness.dart';

/// Pushes the screen to full brightness while the flash step runs so the
/// face reflects more light. No-op on the web.
Future<void> setMaxBrightness(bool on) async {
  if (kIsWeb) return;
  try {
    final sb = ScreenBrightness.instance;
    if (on) {
      await sb.setApplicationScreenBrightness(1.0);
    } else {
      await sb.resetApplicationScreenBrightness();
    }
  } catch (_) {}
}
