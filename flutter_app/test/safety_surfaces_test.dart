import 'package:emotune/screens/legal/legal_screen.dart';
import 'package:emotune/screens/support/support_contact_quick_list.dart';
import 'package:emotune/screens/support/support_screen.dart';
import 'package:emotune/services/api_service.dart';
import 'package:emotune/services/support_contacts.dart';
import 'package:emotune/theme/app_theme.dart';
import 'package:emotune/widgets/emotion_chip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

double contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

/// [overlay] at [alpha] composited onto [base], as the banners paint it.
Color tint(Color overlay, double alpha, Color base) =>
    Color.alphaBlend(overlay.withValues(alpha: alpha), base);

const brandAmber = Color(0xFFFFB020);

void main() {
  group('safety surface contrast (WCAG AA, 4.5:1 for text)', () {
    for (final entry in {
      'light': EmoTuneColors.light,
      'dark': EmoTuneColors.dark,
    }.entries) {
      final c = entry.value;
      final surfaces = {
        'check-in banner': tint(brandAmber, 0.10, c.background),
        'crisis card': tint(brandAmber, 0.12, c.background),
        'support page': c.background,
        'contact card': c.card,
      };
      for (final surface in surfaces.entries) {
        test('${entry.key}: safety and secondary text on ${surface.key}', () {
          expect(contrast(c.safety, surface.value), greaterThanOrEqualTo(4.5));
          expect(
            contrast(c.textSecondary, surface.value),
            greaterThanOrEqualTo(4.5),
          );
          expect(
            contrast(c.textPrimary, surface.value),
            greaterThanOrEqualTo(4.5),
          );
        });
      }
      test('${entry.key}: label on a filled safety button', () {
        expect(contrast(c.onSafety, c.safety), greaterThanOrEqualTo(4.5));
      });
    }
  });

  group('brand and mood colors stay readable', () {
    for (final entry in {
      'light': EmoTuneColors.light,
      'dark': EmoTuneColors.dark,
    }.entries) {
      final c = entry.value;
      test('${entry.key}: accentText on every surface', () {
        for (final surface in [c.background, c.card, c.cardAlt]) {
          expect(contrast(c.accentText, surface), greaterThanOrEqualTo(4.5));
        }
      });
    }

    test('"EmoTune pick" badge: black on lime', () {
      expect(contrast(Colors.black, AppColors.gradientEnd),
          greaterThanOrEqualTo(4.5));
    });

    test('a selected mood chip has readable ink on every mood color', () {
      for (final mood in AppColors.emotionColors.entries) {
        final ink = EmotionChip.inkFor(mood.value);
        expect(contrast(ink, mood.value), greaterThanOrEqualTo(4.5),
            reason: mood.key);
      }
    });
  });

  group('bundled support contacts', () {
    test('are exactly the four verified numbers, emergency first', () {
      expect(
        kBundledSupportContacts.map((c) => c['phone']),
        ['911', '1553', '09173255789', '09189296012'],
      );
    });

    test('stand in when the server sent none', () {
      expect(supportContactsOrBundled(null), hasLength(4));
      expect(supportContactsOrBundled(const []), hasLength(4));
      final server = supportContactsOrBundled([
        {'name': 'Only server row', 'phone': '1553'},
      ]);
      expect(server.single['name'], 'Only server row');
    });
  });

  testWidgets('concern banner list makes every contact tap-to-dial',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildLightTheme(),
      home: Scaffold(
        body: SupportContactQuickList(
          resources: supportContactsOrBundled(null),
        ),
      ),
    ));

    expect(find.bySemanticsLabel('Call Emergency services (911), 911'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Call NCMH Crisis Hotline, 1553'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Call Music Cares Studio (Globe), 09173255789'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Call Music Cares Studio (Smart), 09189296012'),
        findsOneWidget);
  });

  group('support screen offline', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({
        'resolved_api_base_url': 'http://emotune.test/api',
      });
      ApiService.httpClient = MockClient(
        (_) async => throw http.ClientException('offline'),
      );
    });

    tearDown(() => ApiService.httpClient = http.Client());

    testWidgets('lists the bundled contacts when the fetch fails',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: buildDarkTheme(),
        home: const SupportScreen(level: 'concern', message: 'Offline test'),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Emergency services (911)'), findsOneWidget);
      expect(find.text('NCMH Crisis Hotline'), findsOneWidget);
      expect(find.text('Call 1553'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Music Cares Studio (Smart)'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Music Cares Studio (Smart)'), findsOneWidget);
    });

    testWidgets('does not address a worried friend as the person at risk',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: buildDarkTheme(),
        home: const SupportScreen(
          level: 'crisis',
          message: 'For your friend',
          about: 'someone_else',
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text("You don't have to go through this alone"), findsNothing);
      expect(find.text("You're doing the right thing by asking"), findsOneWidget);
    });
  });

  testWidgets('privacy policy is in the app, marked draft, and names Gemini',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildDarkTheme(),
      home: const LegalScreen(doc: LegalDoc.privacy),
    ));

    expect(find.textContaining('DRAFT'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('Google Gemini'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('not your name, email or account ID'),
        findsOneWidget);
  });
}
