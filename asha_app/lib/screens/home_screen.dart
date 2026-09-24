import 'package:flutter/material.dart';

import '../api.dart';
import '../db.dart';
import 'questionnaire_screen.dart';
import 'transcript_screen.dart';
import 'triage_widgets.dart';

class HomeScreen extends StatefulWidget {
  final String username;
  const HomeScreen({super.key, required this.username});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;
  int pending = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    final n = await Db.pendingCount();
    setState(() => pending = n);
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      TriageTab(username: widget.username, onSaved: _refresh),
      RecordsTab(onChanged: _refresh),
      SyncTab(onSynced: _refresh),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text('Genomind ASHA — ${widget.username}'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 14),
            child: Center(child: Badge(
              label: Text('$pending'),
              isLabelVisible: pending > 0,
              child: const Icon(Icons.sync)),
            ),
          ),
        ],
      ),
      body: screens[tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.fact_check), label: 'जांच'),
          NavigationDestination(icon: Icon(Icons.folder_shared), label: 'Records'),
          NavigationDestination(icon: Icon(Icons.cloud_upload), label: 'Sync'),
        ],
      ),
    );
  }
}

class TriageTab extends StatelessWidget {
  final String username;
  final VoidCallback onSaved;
  const TriageTab({super.key, required this.username, required this.onSaved});

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(18), children: [
      Card(child: ListTile(
        leading: const Icon(Icons.quiz, size: 34, color: Color(0xFF0F62FE)),
        title: const Text('प्रश्नावली जांच',
            style: TextStyle(fontWeight: FontWeight.bold)),
        subtitle: const Text(
            'Answer guided yes/no questions about the child. Works fully offline.'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () async {
          await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => QuestionnaireScreen(username: username),
          ));
          onSaved();
        },
      )),
      const SizedBox(height: 10),
      Card(child: ListTile(
        leading: const Icon(Icons.mic, size: 34, color: Color(0xFF0F62FE)),
        title: const Text('आवाज़ से जांच',
            style: TextStyle(fontWeight: FontWeight.bold)),
        subtitle: const Text(
            'Speak the family\'s description; the transcript is analyzed for red-flag signs.'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () async {
          await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => TranscriptScreen(username: username),
          ));
          onSaved();
        },
      )),
      const SizedBox(height: 20),
      const Card(color: Color(0xFFE8F0FE), child: Padding(
        padding: EdgeInsets.all(14),
        child: Text('यह जांच केवल रेफरल में मदद के लिए है — यह निदान नहीं है। '
            'This triage supports referral decisions; it is not a diagnosis.',
            style: TextStyle(fontSize: 13)),
      )),
    ]);
  }
}

class RecordsTab extends StatelessWidget {
  final VoidCallback onChanged;
  const RecordsTab({super.key, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, Object?>>>(
      future: Db.recent(),
      builder: (ctx, snap) {
        if (!snap.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final rows = snap.data!;
        if (rows.isEmpty) {
          return const Center(child: Text('अभी कोई रिकॉर्ड नहीं / No records yet'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(14),
          itemCount: rows.length,
          itemBuilder: (ctx, i) {
            final r = rows[i];
            final color = triageColor(r['triage_color'] as String?);
            return Card(child: ListTile(
              leading: CircleAvatar(backgroundColor: color, radius: 8),
              title: Text('रोगी age ${(r['patient_age'] ?? '?')} · ${r['village'] ?? ''}'),
              subtitle: Text('${r['reported_symptoms'] ?? ''}\n${r['created_at'] ?? ''}',
                  style: const TextStyle(fontSize: 12)),
              isThreeLine: true,
              trailing: (r['sync_state'] == 'synced')
                  ? const Icon(Icons.check_circle, color: Colors.green)
                  : const Icon(Icons.cloud_upload, color: Colors.orange),
            ));
          },
        );
      },
    );
  }
}

class SyncTab extends StatefulWidget {
  final VoidCallback onSynced;
  const SyncTab({super.key, required this.onSynced});

  @override
  State<SyncTab> createState() => _SyncTabState();
}

class _SyncTabState extends State<SyncTab> {
  String? msg;

  Future<void> _sync() async {
    setState(() { msg = 'भेज रहे हैं... / sending...'; });
    try {
      final rows = await Db.pending();
      if (rows.isEmpty) {
        setState(() => msg = 'सब भेजा गया / Everything already synced');
        return;
      }
      final payload = rows.map(Db.toPayload).toList();
      final res = await Api.post('/triage/sync', payload);
      await Db.markSynced(rows.map((r) => r['local_id'] as String).toList());
      final alerts = (res['community_alerts'] as Map?)?['alerts'] as List? ?? [];
      setState(() {
        msg = '✓ ${res['accepted_records'] ?? rows.length} records synced'
            '${alerts.isEmpty ? '' : ' · ${alerts.length} community alert(s) in your district!'}';
      });
      widget.onSynced();
    } on AuthException {
      setState(() => msg = 'कृपया दोबारा लॉग इन करें / Please sign in again');
    } catch (e) {
      setState(() => msg = 'नेटवर्क नहीं — बाद में कोशिश करें / Offline — will retry later');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Center(child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.cloud_upload, size: 54, color: Color(0xFF0F62FE)),
        const SizedBox(height: 12),
        const Text('Send saved records to the hospital server when internet is available.',
            textAlign: TextAlign.center),
        const SizedBox(height: 18),
        FilledButton.icon(onPressed: _sync, icon: const Icon(Icons.send), label: const Text('अभी भेजें / Sync now')),
        if (msg != null) Padding(
          padding: const EdgeInsets.only(top: 14),
          child: Text(msg!, textAlign: TextAlign.center),
        ),
      ]),
    ));
  }
}
