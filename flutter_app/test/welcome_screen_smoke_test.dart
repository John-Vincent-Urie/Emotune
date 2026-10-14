import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:emotune/screens/auth/welcome_screen.dart';

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);

  Widget host({bool reduceMotion = false}) => MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: const MaterialApp(home: WelcomeScreen()),
      );

  testWidgets('renders and animates', (tester) async {
    await tester.pumpWidget(host());
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump(const Duration(milliseconds: 1200));
    expect(find.text('EmoTune'), findsOneWidget);
    expect(find.text('Create an account'), findsOneWidget);
    expect(find.text('Login'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('honours reduced motion and disposes cleanly', (tester) async {
    await tester.pumpWidget(host(reduceMotion: true));
    await tester.pumpAndSettle();
    expect(find.text('EmoTune'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    expect(tester.takeException(), isNull);
  });

  testWidgets('each fine-print link opens its own document', (tester) async {
    // Phone-sized, so the fine print is on screen rather than scrolled away.
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(host(reduceMotion: true));
    await tester.pumpAndSettle();

    // Two separate link nodes, not one merged span.
    expect(
      tester.getSemantics(find.bySemanticsLabel('terms')),
      matchesSemantics(label: 'terms', isLink: true, hasTapAction: true),
    );
    expect(
      tester.getSemantics(find.bySemanticsLabel('privacy policy')),
      matchesSemantics(label: 'privacy policy', isLink: true, hasTapAction: true),
    );

    await tester.tap(find.text('terms'));
    await tester.pumpAndSettle();
    expect(find.text('Terms of Use'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('privacy policy'));
    await tester.pumpAndSettle();
    expect(find.text('Privacy Policy'), findsOneWidget);
    handle.dispose();
  });
}
