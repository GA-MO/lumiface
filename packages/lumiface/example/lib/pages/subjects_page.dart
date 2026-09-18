import 'package:lumiface/lumiface.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../main.dart';

class SubjectsPage extends StatefulWidget {
  const SubjectsPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<SubjectsPage> createState() => _SubjectsPageState();
}

class _SubjectsPageState extends State<SubjectsPage> {
  List<Subject>? _rows;
  String? _error;

  Future<void> _load() async {
    try {
      final rows = await widget.settings.client.listSubjects();
      setState(() {
        _rows = rows;
        _error = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _enrollFromGallery() async {
    final idCtrl = TextEditingController(text: widget.settings.subjectId);
    final nameCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Enrol from a photo'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: idCtrl, decoration: const InputDecoration(labelText: 'Subject id')),
          TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'Name')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Pick photo')),
        ],
      ),
    );
    if (ok != true || idCtrl.text.isEmpty) return;
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 1600, imageQuality: 92);
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final e = await widget.settings.client
          .enroll(externalId: idCtrl.text, name: nameCtrl.text, photoJpeg: bytes, replace: true);
      messenger.showSnackBar(SnackBar(content: Text('Enrolled ${e.externalId} (spoof ${fmt(e.enrollSpoofScore)})')));
      await _load();
    } on LumifaceException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Rejected: ${e.reasonCode} ${e.details ?? ''}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Subjects'), actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ]),
        floatingActionButton: FloatingActionButton(
          onPressed: _enrollFromGallery,
          tooltip: 'Enrol from a photo (use the camera flow on the Use cases tab for a live enrolment)',
          child: const Icon(Icons.add_photo_alternate),
        ),
        body: _error != null
            ? Center(child: Text(_error!))
            : _rows == null
                ? Center(child: FilledButton(onPressed: _load, child: const Text('Load')))
                : ListView(
                    children: [
                      for (final e in _rows!)
                        ListTile(
                          title: Text(e.externalId),
                          subtitle: Text('${e.name}  · enrol spoof ${fmt(e.enrollSpoofScore)}'),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              await widget.settings.client.deleteSubject(e.externalId);
                              await _load();
                            },
                          ),
                          onTap: () => widget.settings.save(subjectId: e.externalId),
                        ),
                    ],
                  ),
      );
}
