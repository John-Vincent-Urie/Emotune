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
              checkInFrequencyTracks: null,
              onCheckInFrequencyChanged: (_) {},
              familiarity: 'balanced',
              onFamiliarityChanged: (_) {},
              preferInstrumental: false,
              onPreferInstrumentalChanged: (_) {},
              trainOnThisSession: true,
              onTrainOnThisSessionChanged: (_) {},
            ),
          ),
        ),
      );
    }

    // 'Auto' labels both the Session Length and Check-In Rhythm rows, so chip
    // lookups are scoped to the first Wrap, which is the session length row.
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

      expect(find.text('Session Length'), findsOneWidget);
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

      ChoiceChip chipFor(String label) => tester.widget<ChoiceChip>(
            find.ancestor(
              of: lengthChip(label),
              matching: find.byType(ChoiceChip),
            ),
          );

      expect(chipFor('20 min').selected, isTrue);
      expect(chipFor('Auto').selected, isFalse);
      expect(chipFor('15 min').selected, isFalse);
      expect(chipFor('45 min').selected, isFalse);
    });

    testWidgets('outcome mode section stays hidden in the profile config',
        (tester) async {
      await tester.pumpWidget(wrap(
        sessionLengthMinutes: 15,
        onSessionLengthChanged: (_) {},
      ));

      expect(find.text('Outcome Mode'), findsNothing);
      expect(find.text('Match My Mood'), findsNothing);
      expect(find.text('Session Length'), findsOneWidget);
    });
  });
}
