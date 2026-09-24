import 'package:flutter/material.dart';

Color triageColor(String? c) {
  switch ((c ?? '').toLowerCase()) {
    case 'red': return const Color(0xFFC21F2C);
    case 'yellow': return const Color(0xFFE0A800);
    default: return const Color(0xFF0E8345);
  }
}

/// Big result card shown after triage: color, what to do (Hindi + English),
/// where to go. Persisted via onRecord when the ASHA saves it.
class TriageResultCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final VoidCallback? onSave;

  const TriageResultCard({super.key, required this.result, this.onSave});

  @override
  Widget build(BuildContext context) {
    final color = triageColor(result['triage_color'] as String?);
    return Card(
      color: color.withOpacity(0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(backgroundColor: color, radius: 10),
            const SizedBox(width: 10),
            Text(
              result['triage_color'] == 'red'
                  ? 'URGENT — तुरंत अस्पताल जाएँ'
                  : result['triage_color'] == 'yellow'
                      ? 'REFER — 3 दिन में PHC जाएँ'
                      : 'MONITOR — घर पर देखभाल',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: color),
            ),
          ]),
          const SizedBox(height: 10),
          Text(result['recommendation_hi'] ?? '',
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(result['recommendation'] ?? '', style: const TextStyle(fontSize: 13)),
          const Divider(height: 22),
          Text('कहाँ जाएँ / Where: ${result['referral_facility'] ?? '—'}',
              style: const TextStyle(fontWeight: FontWeight.w600)),
          if ((result['reported_symptoms'] as List?)?.isNotEmpty == true) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final s in result['reported_symptoms'] as List)
                Chip(label: Text(s.toString(), style: const TextStyle(fontSize: 12)),
                     visualDensity: VisualDensity.compact),
            ]),
          ],
          const SizedBox(height: 10),
          Text(result['disclaimer'] ?? '',
              style: const TextStyle(fontSize: 11, color: Colors.black54)),
          if (onSave != null) ...[
            const SizedBox(height: 8),
            SizedBox(width: double.infinity, child: FilledButton.icon(
              onPressed: onSave,
              icon: const Icon(Icons.save),
              label: const Text('सेव करें (offline) / Save record'),
            )),
          ],
        ]),
      ),
    );
  }
}
