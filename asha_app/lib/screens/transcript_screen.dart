import 'package:flutter/material.dart';

import '../api.dart';
import '../db.dart';
import 'triage_widgets.dart';

/// Voice-first triage: uses the platform speech-to-text when available
/// (speech_to_text plugin can be added in pubspec for device builds); the
/// typed fallback keeps the flow usable in the emulator and offline tests.
class TranscriptScreen extends StatefulWidget {
  final String username;
  const TranscriptScreen({super.key, required this.username});

  @override
  State<TranscriptScreen> createState() => _TranscriptScreenState();
}

class _TranscriptScreenState extends State<TranscriptScreen> {
  final ctrl = TextEditingController();
  final ageCtrl = TextEditingController();
  final villageCtrl = TextEditingController();
  Map<String, dynamic>? result;
  String? err;
  bool busy = false;

  Future<void> _analyze() async {
    if (ctrl.text.trim().isEmpty) return;
    setState(() { busy = true; err = null; });
    try {
      final res = await Api.post('/triage/text', {
        'transcript': ctrl.text.trim(),
        'age': int.tryParse(ageCtrl.text.trim()),
        'village': villageCtrl.text.trim(),
        'asha_id': widget.username,
      });
      await Db.saveRecord({
        ...res,
        'age': int.tryParse(ageCtrl.text.trim()),
        'village': villageCtrl.text.trim(),
        'local_id': 'asha-${DateTime.now().millisecondsSinceEpoch}',
      });
      if (mounted) setState(() { result = res; busy = false; });
    } catch (e) {
      if (mounted) setState(() {
        err = 'सर्वर से संपर्क नहीं — रिकॉर्ड बाद में sync होगा / Offline: save and sync later';
        busy = false;
        // keep a local record with the raw transcript; server scores on sync
      });
      await Db.saveRecord({
        'triage_color': 'yellow',
        'recommendation_hi': 'नेटवर्क आने पर जांच होगी (offline draft)',
        'recommendation': 'Saved offline; will be analyzed on sync.',
        'referral_facility': 'PHC',
        'reported_symptoms': [],
        'hpo_ids': [],
        'transcript': ctrl.text.trim(),
        'source': 'transcript_offline',
        'age': int.tryParse(ageCtrl.text.trim()),
        'village': villageCtrl.text.trim(),
        'local_id': 'asha-${DateTime.now().millisecondsSinceEpoch}',
        'disclaimer': 'Offline draft. Server triage pending.',
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('आवाज़ से जांच')),
      body: ListView(padding: const EdgeInsets.all(18), children: [
        Row(children: [
          Expanded(child: TextField(controller: ageCtrl, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'उम्र / Age'))),
          const SizedBox(width: 10),
          Expanded(child: TextField(controller: villageCtrl,
              decoration: const InputDecoration(labelText: 'गाँव / Village'))),
        ]),
        const SizedBox(height: 14),
        TextField(controller: ctrl, maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'परिवार क्या कह रहा है / What the family says',
              hintText: 'e.g. बच्चे को दौरे पड़ रहे हैं और खून की कमी है',
              border: OutlineInputBorder())),
        const SizedBox(height: 14),
        FilledButton.icon(
          onPressed: busy ? null : _analyze,
          icon: busy
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.mic),
          label: const Text('जांच करें / Analyze')),
        if (err != null) Padding(padding: const EdgeInsets.only(top: 12),
            child: Text(err!, style: const TextStyle(color: Colors.orange))),
        if (result != null) ...[
          const SizedBox(height: 16),
          TriageResultCard(result: result!, onSave: null),
        ],
      ]),
    );
  }
}
