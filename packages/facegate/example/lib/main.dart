import 'package:facegate/facegate.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'pages/history_page.dart';
import 'pages/settings_page.dart';
import 'pages/subjects_page.dart';
import 'pages/usecases_page.dart';

void main() => runApp(const App());

class AppSettings extends ChangeNotifier {
  AppSettings(this._prefs);
  final SharedPreferences _prefs;

  String get baseUrl => _prefs.getString('baseUrl') ?? 'http://localhost:8000';
  String get apiKey => _prefs.getString('apiKey') ?? 'change-me';
  String get subjectId => _prefs.getString('subjectId') ?? '';
  bool get debug => _prefs.getBool('debug') ?? false;
  bool get thai => _prefs.getBool('thai') ?? false;

  LivenessStrings get strings => thai ? LivenessStrings.th : LivenessStrings.en;

  Future<void> save({String? baseUrl, String? apiKey, String? subjectId, bool? debug, bool? thai}) async {
    if (baseUrl != null) await _prefs.setString('baseUrl', baseUrl);
    if (apiKey != null) await _prefs.setString('apiKey', apiKey);
    if (subjectId != null) await _prefs.setString('subjectId', subjectId);
    if (debug != null) await _prefs.setBool('debug', debug);
    if (thai != null) await _prefs.setBool('thai', thai);
    notifyListeners();
  }

  FacegateClient get client => FacegateClient(baseUrl: baseUrl, apiKey: apiKey);
}

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Facegate',
        theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
        home: FutureBuilder(
          future: SharedPreferences.getInstance(),
          builder: (_, snap) => snap.hasData
              ? Home(settings: AppSettings(snap.data!))
              : const Scaffold(body: Center(child: CircularProgressIndicator())),
        ),
      );
}

class Home extends StatefulWidget {
  const Home({super.key, required this.settings});
  final AppSettings settings;

  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    widget.settings.addListener(_refresh);
  }

  void _refresh() => setState(() {});

  @override
  void dispose() {
    widget.settings.removeListener(_refresh);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      UseCasesPage(settings: widget.settings),
      SubjectsPage(settings: widget.settings),
      HistoryPage(settings: widget.settings),
      SettingsPage(settings: widget.settings),
    ];
    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.face), label: 'Use cases'),
          NavigationDestination(icon: Icon(Icons.people), label: 'Subjects'),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}

String fmt(double? v) => v?.toStringAsFixed(3) ?? '-';
