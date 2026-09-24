import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:asha_app/screens/triage_widgets.dart';

void main() {
  testWidgets('triage result card shows color and recommendation', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: TriageResultCard(result: const {
          'triage_color': 'red',
          'recommendation_hi': 'आज ही जिला अस्पताल जाएँ।',
          'recommendation': 'Urgent referral today.',
          'referral_facility': 'District Hospital',
          'reported_symptoms': <String>['seizure'],
          'disclaimer': 'Not a diagnosis.',
        }),
      ),
    ));
    expect(find.textContaining('URGENT'), findsOneWidget);
    expect(find.textContaining('District Hospital'), findsOneWidget);
  });
}
