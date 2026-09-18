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
    subtitle: 'Verify the saved subject id, purpose "checkin", Thai or English strings from Settings.',
    icon: Icons.badge,
    open: (context, s) => pushFlow(
      context,
      (done) => FaceVerifyView(
        client: s.client,
        subjectId: s.subjectId,
        purpose: 'checkin',
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
        subjectId: s.subjectId,
        purpose: 'login',
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
    subtitle: 'No subject id: proves a live person, nothing to match against.',
    icon: Icons.sensors,
    open: (context, s) => pushFlow(
      context,
      (done) => FaceVerifyView(
        client: s.client,
        purpose: 'kiosk',
        strings: s.strings,
        showDebug: s.debug,
        onResult: done,
        onFlashChanged: setMaxBrightness,
      ),
    ),
  ),
  UseCase(
    title: 'Enrol from the camera',
    subtitle: 'FaceFlow.enroll: align, capture one frontal frame, POST /v1/subjects.',
    icon: Icons.person_add_alt_1,
    open: (context, s) async {
      final id = await askText(context, 'Subject id to enrol', initial: s.subjectId);
      if (id == null || id.isEmpty || !context.mounted) return null;
      return pushFlow(
        context,
        (done) => FaceVerifyView(
          client: s.client,
          flow: FaceFlow.enroll,
          subjectId: id,
          replaceEnrollment: true,
          strings: s.strings,
          showDebug: s.debug,
          onResult: done,
        ),
      );
    },
  ),
  UseCase(
    title: 'Custom UI (headless)',
    subtitle: 'overlayBuilder draws its own guide, prompts and result card from FaceVerifyScope.',
    icon: Icons.brush,
    open: (context, s) => pushFlow(context, (done) => CustomUiPage(settings: s, onResult: done)),
  ),
];

Future<String?> askText(BuildContext context, String label, {String initial = ''}) {
  final ctrl = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(label),
      content: TextField(controller: ctrl, autofocus: true),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: const Text('OK')),
      ],
    ),
  );
}

class UseCasesPage extends StatefulWidget {
  const UseCasesPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<UseCasesPage> createState() => _UseCasesPageState();
}

class _UseCasesPageState extends State<UseCasesPage> {
  VerifyResult? _last;
  String? _lastTitle;

  Future<void> _open(UseCase u) async {
    final s = widget.settings;
    final needsSubject = u.title.startsWith('Attendance') || u.title.startsWith('Login');
    if (needsSubject && s.subjectId.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Set a subject id in Settings')));
      return;
    }
    final r = await u.open(context, s);
    if (mounted) {
      setState(() {
        _last = r;
        _lastTitle = u.title;
      });
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
                              '${r.subject != null ? ' subject ${r.subject!.externalId}' : ''}'
                          : 'FAILED ${r.reasonCode}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (r.message != null) Text(r.message!),
                    Text('match=${fmt(r.scores.match)}  spoof=${fmt(r.scores.spoof)}  '
                        'consistency=${fmt(r.scores.consistency)}'),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
