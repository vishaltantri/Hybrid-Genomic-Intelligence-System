import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../db.dart';
import 'triage_widgets.dart';

/// Guided questionnaire triage. Questions come from the server cache so the
/// flow works fully offline; scoring happens server-side when online.
class QuestionnaireScreen extends StatefulWidget {
  final String username;
  const QuestionnaireScreen({super.key, required this.username});

  @override
  State<QuestionnaireScreen> createState() => _QuestionnaireScreenState();
}

class _QuestionnaireScreenState extends State<QuestionnaireScreen> {
  List<Map<String, dynamic>> questions = [];
  final Map<String, String> answers = {};
  int step = 0;
  Map<String, dynamic>? result;
  bool offlineMode = false;
  final ageCtrl = TextEditingController();
  final villageCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    Map<String, dynamic>? q = await Api.cachedQuestionnaire();
    if (q == null) {
      try {
        await Api.cacheQuestionnaire();
        q = await Api.cachedQuestionnaire();
      } catch (_) {
        setState(() => offlineMode = true);
        return;
      }
    }
    setState(() {
      questions = ((q?['questions'] as List?) ?? [])
          .map((e) => e as Map<String, dynamic>)
          .toList();
    });
  }

  Future<void> _submit() async {
    final payload = {
      'answers': answers,
      'age': int.tryParse(ageCtrl.text.trim()),
      'village': villageCtrl.text.trim(),
      'asha_id': widget.username,
    };
    try {
      final res = await Api.post('/triage/answers', payload);
      await _save(res);
    } catch (_) {
      // offline: local rule mirror — red flags answered "haan" escalate.
      final flags = questions.where((q) {
        final rf = q['red_flag'] as String?;
        return rf != null && answers[q['id']] == 'haan';
      }).toList();
      final color = flags.isNotEmpty ? 'red' : (answers.values.contains('haan') ? 'yellow' : 'green');
      await _save({
        'triage_color': color,
        'recommendation_hi': color == 'red'
            ? 'आज ही जिला अस्पताल जाएँ (offline rule)'
            : 'नज़दीकी स्वास्थ्य केंद्र दिखाएँ (offline rule)',
        'recommendation': color == 'red'
            ? 'Urgent referral today (offline rule).'
            : 'Refer to PHC (offline rule).',
        'referral_facility': color == 'red' ? 'District Hospital' : 'PHC',
        'reported_symptoms': questions
            .where((q) => answers[q['id']] == 'haan')
            .map((q) => q['en'] ?? q['id'])
            .toList(),
        'hpo_ids': <String>[],
        'source': 'questionnaire_offline',
        'disclaimer': 'Offline rule-based triage. Not a diagnosis.',
      });
    }
  }

  Future<void> _save(Map<String, dynamic> res) async {
    await Db.saveRecord({
      ...res,
      'age': int.tryParse(ageCtrl.text.trim()),
      'village': villageCtrl.text.trim(),
      'local_id': 'asha-${DateTime.now().millisecondsSinceEpoch}',
    });
    if (mounted) setState(() => result = res);
  }

  @override
  Widget build(BuildContext context) {
    if (offlineMode && questions.isEmpty) {
      return Scaffold(appBar: AppBar(title: const Text('जांच')),
          body: const Center(child: Text(
            'प्रश्नावली उपलब्ध नहीं है — एक बार इंटरनेट से जुड़कर लॉगिन करें।\n'
            'No cached questionnaire yet — sign in once while online.',
            textAlign: TextAlign.center)));
    }
    if (result != null) {
      return Scaffold(appBar: AppBar(title: const Text('नतीजा / Result')), body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TriageResultCard(result: result!, onSave: null),
          const SizedBox(height: 14),
          OutlinedButton(onPressed: () => Navigator.of(context).pop(),
              child: const Text('होम / Done')),
        ],
      ));
    }
    if (questions.isEmpty) {
      return Scaffold(appBar: AppBar(title: const Text('जांच')),
          body: const Center(child: CircularProgressIndicator()));
    }

    final q = questions[step];
    final isLast = step == questions.length - 1;
    return Scaffold(
      appBar: AppBar(title: Text('जांच  ${step + 1}/${questions.length}')),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        if (step == 0) ...[
          TextField(controller: ageCtrl, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'बच्चे की उम्र / Child age (years)')),
          const SizedBox(height: 10),
          TextField(controller: villageCtrl,
              decoration: const InputDecoration(labelText: 'गाँव / Village')),
          const SizedBox(height: 18),
        ],
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(q['hi'] ?? q['id'].toString(),
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
            if (q['en'] != null) Text(q['en'], style: const TextStyle(color: Colors.black54)),
          ],
        ))),
        const SizedBox(height: 14),
        Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          Expanded(child: OutlinedButton.icon(
            onPressed: () => _answer('nahi'),
            icon: const Icon(Icons.close), label: const Text('नहीं / No'))),
          const SizedBox(width: 12),
          Expanded(child: FilledButton.icon(
            onPressed: () => _answer('haan'),
            icon: const Icon(Icons.check), label: const Text('हाँ / Yes'))),
        ]),
        if (q['allow_partial'] == true) ...[
          const SizedBox(height: 10),
          Center(child: TextButton(
            onPressed: () => _answer('thoda'),
            child: const Text('कभी-कभी / Sometimes'))),
        ],
      ]),
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(children: [
          if (step > 0) IconButton(
            onPressed: () => setState(() { step--; }),
            icon: const Icon(Icons.arrow_back)),
          const Spacer(),
          FilledButton(
            onPressed: isLast ? _submit : null,
            child: const Text('जमा करें / Submit')),
        ]),
      ),
    );
  }

  void _answer(String a) {
    answers[questions[step]['id'].toString()] = a;
    if (step == questions.length - 1) {
      _submit();
    } else {
      setState(() => step++);
    }
  }
}
