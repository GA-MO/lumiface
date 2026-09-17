import 'package:face_checkin/face_checkin.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const App());

class Settings extends ChangeNotifier {
  Settings(this._prefs);
  final SharedPreferences _prefs;

  String get baseUrl => _prefs.getString('baseUrl') ?? 'http://localhost:8000';
  String get apiKey => _prefs.getString('apiKey') ?? 'change-me';
  String get employeeId => _prefs.getString('employeeId') ?? '';
  bool get debug => _prefs.getBool('debug') ?? false;

  Future<void> save({String? baseUrl, String? apiKey, String? employeeId, bool? debug}) async {
    if (baseUrl != null) await _prefs.setString('baseUrl', baseUrl);
    if (apiKey != null) await _prefs.setString('apiKey', apiKey);
    if (employeeId != null) await _prefs.setString('employeeId', employeeId);
    if (debug != null) await _prefs.setBool('debug', debug);
    notifyListeners();
  }

  CheckinApi get api => CheckinApi(baseUrl: baseUrl, apiKey: apiKey);
}

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Face Check-in',
        theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
        home: FutureBuilder(
          future: SharedPreferences.getInstance(),
          builder: (_, snap) => snap.hasData
              ? Home(settings: Settings(snap.data!))
              : const Scaffold(body: Center(child: CircularProgressIndicator())),
        ),
      );
}

class Home extends StatefulWidget {
  const Home({super.key, required this.settings});
  final Settings settings;

  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    widget.settings.addListener(() => setState(() {}));
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      CheckinTab(settings: widget.settings),
      EmployeesTab(settings: widget.settings),
      HistoryTab(settings: widget.settings),
      SettingsTab(settings: widget.settings),
    ];
    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.face), label: 'Check-in'),
          NavigationDestination(icon: Icon(Icons.people), label: 'Employees'),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}

class CheckinTab extends StatefulWidget {
  const CheckinTab({super.key, required this.settings});
  final Settings settings;

  @override
  State<CheckinTab> createState() => _CheckinTabState();
}

class _CheckinTabState extends State<CheckinTab> {
  CheckinResult? _last;

  Future<void> _start() async {
    final id = widget.settings.employeeId;
    if (id.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Set employee id in Settings')));
      return;
    }
    CheckinResult? result;
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => FaceCheckinScreen(
        api: widget.settings.api,
        employeeId: id,
        strings: LivenessStrings.th,
        showDebug: widget.settings.debug,
        onResult: (r) => result = r,
      ),
    ));
    if (mounted) setState(() => _last = result);
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.settings;
    final r = _last;
    return Scaffold(
      appBar: AppBar(title: const Text('Face Check-in')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('Employee: ${s.employeeId.isEmpty ? '(not set)' : s.employeeId}'),
            const SizedBox(height: 24),
            FilledButton.icon(onPressed: _start, icon: const Icon(Icons.camera_alt), label: const Text('Check in')),
            const SizedBox(height: 32),
            if (r != null)
              Card(
                margin: const EdgeInsets.all(24),
                color: r.ok ? Colors.green.shade50 : Colors.red.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(r.ok ? 'OK (check-in #${r.checkinId})' : 'FAILED: ${r.reasonCode}',
                          style: Theme.of(context).textTheme.titleMedium),
                      if (r.message != null) Text(r.message!),
                      Text('match=${_f(r.scores.match)}  spoof=${_f(r.scores.spoof)}  '
                          'consistency=${_f(r.scores.consistency)}'),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

String _f(double? v) => v?.toStringAsFixed(3) ?? '-';

class EmployeesTab extends StatefulWidget {
  const EmployeesTab({super.key, required this.settings});
  final Settings settings;

  @override
  State<EmployeesTab> createState() => _EmployeesTabState();
}

class _EmployeesTabState extends State<EmployeesTab> {
  List<Employee>? _rows;
  String? _error;

  Future<void> _load() async {
    try {
      final rows = await widget.settings.api.listEmployees();
      setState(() {
        _rows = rows;
        _error = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _enroll() async {
    final idCtrl = TextEditingController(text: widget.settings.employeeId);
    final nameCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Enroll employee'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: idCtrl, decoration: const InputDecoration(labelText: 'Employee id')),
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
      final e = await widget.settings.api.enroll(
          externalId: idCtrl.text, name: nameCtrl.text, photoJpeg: bytes, replace: true);
      messenger.showSnackBar(SnackBar(content: Text('Enrolled ${e.externalId} (spoof ${_f(e.enrollSpoofScore)})')));
      await _load();
    } on EnrollException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Rejected: ${e.reasonCode} ${e.details ?? ''}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Employees'), actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ]),
        floatingActionButton: FloatingActionButton(onPressed: _enroll, child: const Icon(Icons.person_add)),
        body: _error != null
            ? Center(child: Text(_error!))
            : _rows == null
                ? Center(child: FilledButton(onPressed: _load, child: const Text('Load')))
                : ListView(
                    children: [
                      for (final e in _rows!)
                        ListTile(
                          title: Text(e.externalId),
                          subtitle: Text('${e.name}  · enroll spoof ${_f(e.enrollSpoofScore)}'),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              await widget.settings.api.deleteEmployee(e.externalId);
                              await _load();
                            },
                          ),
                          onTap: () => widget.settings.save(employeeId: e.externalId),
                        ),
                    ],
                  ),
      );
}

class HistoryTab extends StatefulWidget {
  const HistoryTab({super.key, required this.settings});
  final Settings settings;

  @override
  State<HistoryTab> createState() => _HistoryTabState();
}

class _HistoryTabState extends State<HistoryTab> {
  List<CheckinRecord>? _rows;

  Future<void> _load() async {
    final rows = await widget.settings.api.listCheckins();
    setState(() => _rows = rows);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('History'), actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ]),
        body: _rows == null
            ? Center(child: FilledButton(onPressed: _load, child: const Text('Load')))
            : ListView(
                children: [
                  for (final r in _rows!)
                    ListTile(
                      leading: Icon(r.ok ? Icons.check_circle : Icons.cancel, color: r.ok ? Colors.green : Colors.red),
                      title: Text('${r.employeeId}  ${r.reasonCode}'),
                      subtitle: Text('${r.createdAt.toLocal()}  match=${_f(r.scores.match)} '
                          'spoof=${_f(r.scores.spoof)} cons=${_f(r.scores.consistency)}'),
                    ),
                ],
              ),
      );
}

class SettingsTab extends StatefulWidget {
  const SettingsTab({super.key, required this.settings});
  final Settings settings;

  @override
  State<SettingsTab> createState() => _SettingsTabState();
}

class _SettingsTabState extends State<SettingsTab> {
  late final _url = TextEditingController(text: widget.settings.baseUrl);
  late final _key = TextEditingController(text: widget.settings.apiKey);
  late final _emp = TextEditingController(text: widget.settings.employeeId);

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Settings')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(controller: _url, decoration: const InputDecoration(labelText: 'Server URL')),
            TextField(controller: _key, decoration: const InputDecoration(labelText: 'API key')),
            TextField(controller: _emp, decoration: const InputDecoration(labelText: 'My employee id')),
            SwitchListTile(
              title: const Text('Debug overlay (face box + signals)'),
              value: widget.settings.debug,
              onChanged: (v) => widget.settings.save(debug: v),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () async {
                await widget.settings.save(baseUrl: _url.text.trim(), apiKey: _key.text.trim(), employeeId: _emp.text.trim());
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved')));
                }
              },
              child: const Text('Save'),
            ),
            const SizedBox(height: 24),
            const Text('Tip: on a real iPhone use your Mac\'s LAN IP for the server URL, e.g. http://192.168.1.10:8000'),
          ],
        ),
      );
}
