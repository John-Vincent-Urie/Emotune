import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:emotune/providers/recommendation_studio_provider.dart';
import 'package:emotune/screens/widgets/recommendation_session_controls.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RecommendationStudioProvider session length', () {
    test('defaults to Auto (null) when nothing is stored', () async {
      SharedPreferences.setMockInitialValues({});
      final studio = RecommendationStudioProvider();
      await studio.load();
      expect(studio.sessionLengthMinutes, isNull);
    });

    test('selecting a length notifies and persists', () async {
      SharedPreferences.setMockInitialValues({});
      final studio = RecommendationStudioProvider();
      await studio.load();

      var notifications = 0;
      studio.addListener(() => notifications++);

      studio.setSessionLengthMinutes(45);
      expect(studio.sessionLengthMinutes, 45);
      expect(notifications, 1);

      // Selecting the same value again is a no-op.
      studio.setSessionLengthMinutes(45);
      expect(notifications, 1);

      await Future<void>.delayed(Duration.zero);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getInt('studio.session_length_minutes'), 45);
    });

    test('reloads the stored length in a fresh provider', () async {
      SharedPreferences.setMockInitialValues({
        'studio.session_length_minutes': 15,
      });
      final studio = RecommendationStudioProvider();
      await studio.load();
      expect(studio.sessionLengthMinutes, 15);
    });

    test('Auto clears the stored key', () async {
      SharedPreferences.setMockInitialValues({
        'studio.session_length_minutes': 20,
      });
      final studio = RecommendationStudioProvider();
      await studio.load();
      expect(studio.sessionLengthMinutes, 20);

      studio.setSessionLengthMinutes(null);
      await Future<void>.delayed(Duration.zero);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.containsKey('studio.session_length_minutes'), isFalse);
    });
  });

  group('RecommendationSessionControls session length chips', () {
    Widget wrap({
      int? sessionLengthMinutes,
      required ValueChanged<int?> onSessionLengthChanged,
    }) {
      return MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: RecommendationSessionControls(
              sessionLengthMinutes: sessionLengthMinutes,
              onSessionLengthChanged: onSessionLengthChanged,
            ),
          ),
        ),
      );
    }

    // Session Length is the first Wrap in the card. Chip lookups stay scoped
    // to it so adding another chip row later cannot quietly match the wrong one.
    Finder lengthChip(String label) => find.descendant(
          of: find.byType(Wrap).first,
          matching: find.text(label),
        );

    testWidgets('renders every length option and reports taps', (tester) async {
      final tapped = <int?>[];
      await tester.pumpWidget(wrap(
        sessionLengthMinutes: null,
        onSessionLengthChanged: tapped.add,
      ));

      expect(find.text('Session length'), findsOneWidget);
      for (final label in ['Auto', '15 min', '20 min', '45 min']) {
        expect(lengthChip(label), findsOneWidget);
      }

      await tester.tap(lengthChip('45 min'));
      await tester.pump();
      expect(tapped, [45]);

      await tester.tap(lengthChip('Auto'));
      await tester.pump();
      expect(tapped, [45, null]);
    });

    testWidgets('marks the active length as selected', (tester) async {
      await tester.pumpWidget(wrap(
        sessionLengthMinutes: 20,
        onSessionLengthChanged: (_) {},
      ));

      // The chips are the design system's segmented pills now, not
      // ChoiceChips; the selected state they announce is what to check.
      bool? isSelected(String label) => tester
          .widget<Semantics>(
            find
                .ancestor(
                  of: lengthChip(label),
                  matching: find.byType(Semantics),
                )
                .first,
          )
          .properties
          .selected;

      expect(isSelected('20 min'), isTrue);
      expect(isSelected('Auto'), isFalse);
      expect(isSelected('15 min'), isFalse);
      expect(isSelected('45 min'), isFalse);
    });

    testWidgets('outcome mode and check-in rhythm are gone', (tester) async {
      // Both were removed from the app: the backend routes the outcome mode
      // from the detected emotion, and the check-in cadence comes from that
      // mode's default. Neither is the user's to set any more.
      await tester.pumpWidget(wrap(
        sessionLengthMinutes: 15,
        onSessionLengthChanged: (_) {},
      ));

      expect(find.text('Outcome Mode'), findsNothing);
      expect(find.text('Match My Mood'), findsNothing);
      expect(find.text('Calm Me Down'), findsNothing);
      expect(find.text('Check-In Rhythm'), findsNothing);
      expect(find.text('Every 3'), findsNothing);
      expect(find.text('Session length'), findsOneWidget);
      // Removed 2026-10-10: the therapist's list plays in its own order.
      expect(find.text('Taste control'), findsNothing);
      expect(find.text('More familiar'), findsNothing);
      expect(find.text('Prefer instrumental'), findsNothing);
    });
  });
}
