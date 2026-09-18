import 'package:facegate/facegate.dart';
import 'package:flutter/material.dart';

import '../main.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final _url = TextEditingController(text: widget.settings.baseUrl);
  late final _key = TextEditingController(text: widget.settings.apiKey);
  late final _subject = TextEditingController(text: widget.settings.subjectId);
  ProjectPolicy? _policy;
  List<PolicyPreset>? _presets;
  String? _policyError;

  Future<void> _loadPolicy() async {
    try {
      final client = widget.settings.client;
      final policy = await client.getPolicy();
      final presets = await client.listPresets();
      setState(() {
        _policy = policy;
        _presets = presets;
        _policyError = null;
      });
    } catch (e) {
      setState(() => _policyError = e.toString());
    }
  }

  Future<void> _applyPreset(String preset) async {
    try {
      final policy = await widget.settings.client.updatePolicy(preset: preset);
      setState(() => _policy = policy);
    } catch (e) {
      setState(() => _policyError = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.settings;
    final policy = _policy;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(controller: _url, decoration: const InputDecoration(labelText: 'Server URL')),
          TextField(controller: _key, decoration: const InputDecoration(labelText: 'Project API key')),
          TextField(controller: _subject, decoration: const InputDecoration(labelText: 'My subject id')),
          SwitchListTile(
            title: const Text('Thai strings'),
            value: s.thai,
            onChanged: (v) => s.save(thai: v),
          ),
          SwitchListTile(
            title: const Text('Debug overlay (face box + signals)'),
            value: s.debug,
            onChanged: (v) => s.save(debug: v),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () async {
              await s.save(baseUrl: _url.text.trim(), apiKey: _key.text.trim(), subjectId: _subject.text.trim());
              if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved')));
            },
            child: const Text('Save'),
          ),
          const Divider(height: 48),
          Row(
            children: [
              Text('Project policy', style: Theme.of(context).textTheme.titleMedium),
              const Spacer(),
              TextButton.icon(onPressed: _loadPolicy, icon: const Icon(Icons.refresh), label: const Text('Load')),
            ],
          ),
          if (_policyError != null) Text(_policyError!, style: const TextStyle(color: Colors.red)),
          if (policy != null && _presets != null) ...[
            Text('Project "${policy.project}", preset ${policy.preset}'
                '${policy.overrides.isEmpty ? '' : ', ${policy.overrides.length} override(s)'}'),
            const SizedBox(height: 8),
            RadioGroup<String>(
              groupValue: policy.preset,
              onChanged: (v) => _applyPreset(v!),
              child: Column(children: [
                for (final p in _presets!)
                  RadioListTile<String>(value: p.name, title: Text(p.name), subtitle: Text(p.summary)),
              ]),
            ),
            const SizedBox(height: 8),
            Text('Effective: match ≥ ${policy.effective['match_threshold']}, '
                '${policy.effective['challenge_count']} challenges, '
                'flash ${policy.effective['flash_enforce'] == true ? 'enforced' : 'shadow'}, '
                'smile ${policy.effective['smile_enforce'] == true ? 'enforced' : 'off'}, '
                'client parallax ${policy.clientConfig.parallaxMinShift}'),
          ],
          const SizedBox(height: 24),
          const Text('Tip: on a phone use your Mac\'s LAN IP for the server URL, e.g. http://192.168.1.10:8000. '
              'On the Android emulator use http://10.0.2.2:8000 and the emulator preset.'),
        ],
      ),
    );
  }
}
