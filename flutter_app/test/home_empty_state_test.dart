import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:emotune/models/mood_option.dart';
import 'package:emotune/models/nav_destination.dart';
import 'package:emotune/screens/home/widgets/home_empty_state.dart';
import 'package:emotune/theme/app_theme.dart';

Future<AnimationController> _pumpEmptyState(
  WidgetTester tester, {
  bool reduceMotion = true,
  Brightness brightness = Brightness.dark,
}) async {
  final controller = AnimationController(
    vsync: tester,
    duration: const Duration(milliseconds: 1000),
  )..value = 1;
  addTearDown(controller.dispose);

  await tester.pumpWidget(
    MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: MaterialApp(
        theme: brightness == Brightness.dark ? buildDarkTheme() : buildLightTheme(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: HomeEmptyState(
              entrance: controller,
              reduceMotion: reduceMotion,
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return controller;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Home empty state', () {
    testWidgets('shows the first suggestion', (tester) async {
      await _pumpEmptyState(tester);

      expect(find.text(kPromptSuggestions.first), findsOneWidget);
    });

    testWidgets('holds still when reduced motion is on', (tester) async {
      // pumpAndSettle would time out if the orb or ring loops were running.
      await _pumpEmptyState(tester);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('reads its colours from the active theme, not from hex',
        (tester) async {
      for (final brightness in [Brightness.light, Brightness.dark]) {
        await _pumpEmptyState(tester, brightness: brightness);

        final expected = brightness == Brightness.light
            ? EmoTuneColors.light
            : EmoTuneColors.dark;
        final prompt = tester.widget<Text>(
          find.text(kPromptSuggestions.first),
        );

        expect(prompt.style!.color, expected.textSecondary,
            reason: '$brightness prompt colour');
      }
    });
  });

  group('Navigation data', () {
    test('exposes the five destinations in order', () {
      expect(
        kNavItems.map((item) => item.label).toList(),
        ['Home', 'Favorites', 'Discover', 'History', 'Profile'],
      );
    });
  });

  group('Theme tokens', () {
    test('light and dark both register EmoTuneColors', () {
      expect(buildLightTheme().extension<EmoTuneColors>(), isNotNull);
      expect(buildDarkTheme().extension<EmoTuneColors>(), isNotNull);
    });

    test('lerp interpolates every token so theme swaps can animate', () {
      final mid = EmoTuneColors.light.lerp(EmoTuneColors.dark, 0.5);

      expect(mid.background, isNot(EmoTuneColors.light.background));
      expect(mid.background, isNot(EmoTuneColors.dark.background));
      expect(mid.textPrimary, isNot(EmoTuneColors.light.textPrimary));
    });
  });
}
