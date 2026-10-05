import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:emotune/providers/auth_provider.dart';
import 'package:emotune/screens/auth/login_register_screen.dart';
import 'package:emotune/widgets/emotune_buttons.dart';

/// The reset screen itself, with motion frozen so pumpAndSettle can be used.
Future<void> _pumpReset(WidgetTester tester, {String initialEmail = ''}) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthProvider>(
      create: (_) => AuthProvider(),
      child: MediaQuery(
        data: const MediaQueryData(disableAnimations: true),
        child: MaterialApp(
          home: ForgotPasswordScreen(initialEmail: initialEmail),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Forgot password', () {
    testWidgets('opens on the email step and explains what will happen',
        (tester) async {
      await _pumpReset(tester);

      expect(find.text('Forgot password'), findsOneWidget);
      expect(
        find.textContaining('we will send you a 6-digit code'),
        findsOneWidget,
      );
      expect(find.text('Send code'), findsOneWidget);
    });

    testWidgets('carries the address over from the login form', (tester) async {
      await _pumpReset(tester, initialEmail: 'robin@example.com');

      expect(find.text('robin@example.com'), findsOneWidget);
    });

    testWidgets('send stays disabled until the email looks like one',
        (tester) async {
      await _pumpReset(tester);
      final button = find.widgetWithText(EmoTunePrimaryButton, 'Send code');

      expect(tester.widget<EmoTunePrimaryButton>(button).onPressed, isNull);

      await tester.enterText(find.byType(TextField).first, 'not-an-email');
      await tester.pumpAndSettle();
      expect(tester.widget<EmoTunePrimaryButton>(button).onPressed, isNull);

      await tester.enterText(find.byType(TextField).first, 'robin@example.com');
      await tester.pumpAndSettle();
      expect(tester.widget<EmoTunePrimaryButton>(button).onPressed, isNotNull);
    });

    testWidgets('offers a way back to login', (tester) async {
      await _pumpReset(tester);

      expect(find.text('Remembered it?'), findsOneWidget);
      expect(find.text('Log in'), findsOneWidget);
    });
  });
}
