import 'package:lumiface/lumiface.dart';
import 'package:flutter/material.dart';

import '../brightness.dart';
import '../main.dart';
import 'custom_ui_page.dart';

class UseCase {
  const UseCase({required this.title, required this.subtitle, required this.icon, required this.open});
  final String title;
  final String subtitle;
  final IconData icon;
  final Future<VerifyResult?> Function(BuildContext context, AppSettings settings) open;
}

Future<VerifyResult?> pushFlow(BuildContext context, Widget Function(void Function(VerifyResult) done) build) async {
  VerifyResult? result;
  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => Scaffold(body: build((r) => result = r))));
  return result;
}

final useCases = <UseCase>[
  UseCase(
    title: 'Attendance check-in',
    subtitle: 'Verify the selected user (its photo is the reference), purpose "checkin", Thai or English strings from Settings.',
    icon: Icons.badge,
    open: (context, s) => pushFlow(
      context,
      (done) => FaceVerifyView(
        client: s.client,
        sessionProvider: () => s.backend.createSession(userId: s.userId, purpose: 'checkin'),
        strings: s.strings.copyWith(success: s.thai ? 'เช็คอินสำเร็จ' : 'Checked in'),
        showDebug: s.debug,
        onResult: done,
        onFlashChanged: setMaxBrightness,
      ),
    ),
  ),
  UseCase(
    title: 'Login with face',
    subtitle: 'Same verify flow, app colours via FaceVerifyTheme.fromScheme and a rounded guide.',
    icon: Icons.login,
    open: (context, s) => pushFlow(
      context,
      (done) => FaceVerifyView(
        client: s.client,
        sessionProvider: () => s.backend.createSession(userId: s.userId, purpose: 'login'),
        strings: s.strings.copyWith(success: 'Welcome back'),
        theme: FaceVerifyTheme.fromScheme(Theme.of(context).colorScheme).copyWith(
          guideShape: FaceGuideShape.roundedRect,
          guideWidthFraction: 0.8,
          guideAspectRatio: 1.2,
        ),
        showDebug: s.debug,
        onResult: done,
        onFlashChanged: setMaxBrightness,
      ),
    ),
  ),
  UseCase(
    title: 'Liveness only (kiosk)',
    subtitle: 'The backend creates the session without a reference photo: proves a live person, nothing to match against.',
    icon: Icons.sensors,
    open: (context, s) => pushFlow(
      context,
      (done) => FaceVerifyView(
        client: s.client,
        flow: FaceFlow.liveness,
        sessionProvider: () => s.backend.createSession(purpose: 'kiosk'),
        strings: s.strings,
        showDebug: s.debug,
        onResult: done,
        onFlashChanged: setMaxBrightness,
      ),
    ),
  ),
  UseCase(
    title: 'Custom UI (headless)',
    subtitle: 'overlayBuilder draws its own guide, prompts and result card from FaceVerifyScope.',
    icon: Icons.brush,
    open: (context, s) => pushFlow(context, (done) => CustomUiPage(settings: s, onResult: done)),
  ),
];

class UseCasesPage extends StatefulWidget {
  const UseCasesPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<UseCasesPage> createState() => _UseCasesPageState();
}

class _UseCasesPageState extends State<UseCasesPage> {
  VerifyResult? _last;
  String? _lastTitle;
  String? _verdict;

  Future<void> _open(UseCase u) async {
    final s = widget.settings;
    final needsUser = u.title.startsWith('Attendance') || u.title.startsWith('Login');
    if (needsUser && s.userId.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Register a user on the Users tab first')));
      return;
    }
    final r = await u.open(context, s);
    if (!mounted) return;
    setState(() {
      _last = r;
      _lastTitle = u.title;
      _verdict = null;
    });
    // What a real app does next: tell the backend, which reads the outcome from Lumiface itself.
    if (r?.sessionId == null) return;
    try {
      final v = await s.backend.done(r!.sessionId!);
      if (mounted) {
        setState(() => _verdict = v == null
            ? 'backend: no upload recorded for this session'
            : 'backend read the session: ok=${v.ok} reason=${v.reasonCode}'
                '${v.verificationId != null ? ' verification #${v.verificationId}' : ''}');
      }
    } catch (e) {
      if (mounted) setState(() => _verdict = 'backend error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _last;
    return Scaffold(
      appBar: AppBar(title: const Text('Lumiface use cases')),
      body: ListView(
        children: [
          for (final u in useCases)
            ListTile(
              leading: Icon(u.icon),
              title: Text(u.title),
              subtitle: Text(u.subtitle),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _open(u),
            ),
          if (r != null)
            Card(
              margin: const EdgeInsets.all(16),
              color: r.ok ? Colors.green.shade50 : Colors.red.shade50,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_lastTitle ?? '', style: Theme.of(context).textTheme.labelMedium),
                    Text(
                      r.ok
                          ? 'OK ${r.mode}${r.verificationId != null ? ' #${r.verificationId}' : ''}'
                          : 'FAILED ${r.reasonCode}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (r.message != null) Text(r.message!),
                    Text('match=${fmt(r.scores.match)}  spoof=${fmt(r.scores.spoof)}  '
                        'consistency=${fmt(r.scores.consistency)}'),
                    if (_verdict != null) ...[
                      const SizedBox(height: 8),
                      Text(_verdict!, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
