import 'package:lumiface/lumiface.dart';
import 'package:flutter/material.dart';

import '../main.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  List<VerificationRecord>? _rows;
  String? _purpose;

  Future<void> _load() async {
    final rows = await widget.settings.backend.listVerifications(purpose: _purpose);
    setState(() => _rows = rows);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Verifications'), actions: [
          PopupMenuButton<String>(
            initialValue: _purpose ?? '',
            onSelected: (v) {
              _purpose = v.isEmpty ? null : v;
              _load();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: '', child: Text('All purposes')),
              PopupMenuItem(value: 'checkin', child: Text('checkin')),
              PopupMenuItem(value: 'login', child: Text('login')),
              PopupMenuItem(value: 'kiosk', child: Text('kiosk')),
              PopupMenuItem(value: 'custom', child: Text('custom')),
            ],
            icon: const Icon(Icons.filter_list),
          ),
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ]),
        body: _rows == null
            ? Center(child: FilledButton(onPressed: _load, child: const Text('Load')))
            : ListView(
                children: [
                  for (final r in _rows!)
                    ListTile(
                      leading: Icon(r.ok ? Icons.check_circle : Icons.cancel, color: r.ok ? Colors.green : Colors.red),
                      title: Text('${r.reference ? 'verify' : 'liveness'}  ${r.reasonCode}'),
                      subtitle: Text('${r.purpose.isEmpty ? '' : '${r.purpose} · '}${r.createdAt.toLocal()}  '
                          'match=${fmt(r.scores.match)} spoof=${fmt(r.scores.spoof)} cons=${fmt(r.scores.consistency)}'),
                    ),
                ],
              ),
      );
}
