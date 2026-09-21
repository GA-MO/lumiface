import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:lumiface/lumiface.dart';

import '../example_backend.dart';
import '../main.dart';

/// The example backend's users: a registration photo each, kept on that backend. Lumiface sees a
/// user's photo only inside a session and keeps nothing; nothing here talks to Lumiface.
class UsersPage extends StatefulWidget {
  const UsersPage({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<UsersPage> createState() => _UsersPageState();
}

class _UsersPageState extends State<UsersPage> {
  List<ExampleUser>? _rows;
  String? _error;

  Future<void> _load() async {
    try {
      final rows = await widget.settings.backend.listUsers();
      setState(() {
        _rows = rows;
        _error = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _register(ImageSource from) async {
    final idCtrl = TextEditingController(text: widget.settings.userId);
    final nameCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(from == ImageSource.camera ? 'Register with the camera' : 'Register from a photo'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: idCtrl, decoration: const InputDecoration(labelText: 'User id')),
          TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'Name')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(from == ImageSource.camera ? 'Take photo' : 'Pick photo')),
        ],
      ),
    );
    if (ok != true || idCtrl.text.isEmpty) return;
    final picked = await ImagePicker().pickImage(
        source: from, preferredCameraDevice: CameraDevice.front, maxWidth: 1600, imageQuality: 92);
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.settings.backend.registerUser(id: idCtrl.text, name: nameCtrl.text, photoJpeg: bytes);
      messenger.showSnackBar(SnackBar(content: Text('Registered ${idCtrl.text}; verify it from the Use cases tab')));
      await widget.settings.save(userId: idCtrl.text);
      await _load();
    } on LumifaceException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Rejected: ${e.reasonCode} ${e.details ?? ''}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Users (example backend)'), actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ]),
        floatingActionButton: Column(mainAxisSize: MainAxisSize.min, children: [
          FloatingActionButton.small(
            heroTag: 'camera',
            onPressed: () => _register(ImageSource.camera),
            tooltip: 'Register with a selfie',
            child: const Icon(Icons.add_a_photo),
          ),
          const SizedBox(height: 8),
          FloatingActionButton(
            heroTag: 'gallery',
            onPressed: () => _register(ImageSource.gallery),
            tooltip: 'Register from a photo',
            child: const Icon(Icons.add_photo_alternate),
          ),
        ]),
        body: _error != null
            ? Center(child: Text(_error!))
            : _rows == null
                ? Center(child: FilledButton(onPressed: _load, child: const Text('Load')))
                : ListView(
                    children: [
                      for (final u in _rows!)
                        ListTile(
                          title: Text(u.id),
                          subtitle: Text(u.name),
                          selected: u.id == widget.settings.userId,
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              await widget.settings.backend.deleteUser(u.id);
                              await _load();
                            },
                          ),
                          onTap: () => widget.settings.save(userId: u.id),
                        ),
                    ],
                  ),
      );
}
