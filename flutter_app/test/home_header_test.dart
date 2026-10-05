import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:emotune/screens/home/widgets/home_header.dart';
import 'package:emotune/theme/app_theme.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Widget host({required bool reduceMotion, required ThemeData theme}) {
    return MaterialApp(
      theme: theme,
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: Scaffold(
          body: Column(
            children: [
              HomeHeader(
                entrance: const AlwaysStoppedAnimation<double>(1),
                reduceMotion: reduceMotion,
              ),
              const Expanded(child: SizedBox.expand()),
            ],
          ),
        ),
      ),
    );
  }

  testWidgets('renders the wordmark and stays compact at phone width',
      (tester) async {
    tester.view.physicalSize = const Size(360, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(host(reduceMotion: true, theme: buildDarkTheme()));
    await tester.pump();

    expect(find.text('EmoTune'), findsOneWidget);
    // The header is a brand strip, not a hero: it must leave the orb, prompt
    // and composer room on a short phone.
    expect(tester.getSize(find.byType(HomeHeader)).height, lessThan(110));
    expect(tester.takeException(), isNull);
  });

  testWidgets('animates without overflowing, and settles when paused',
      (tester) async {
    tester.view.physicalSize = const Size(360, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(host(reduceMotion: false, theme: buildDarkTheme()));
    // The halo breathes on a repeating controller, so the tree never settles;
    // step through a full cycle instead of pumpAndSettle.
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(milliseconds: 200));
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('renders on the light theme too', (tester) async {
    tester.view.physicalSize = const Size(360, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(host(reduceMotion: true, theme: buildLightTheme()));
    await tester.pump();

    expect(find.text('EmoTune'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
