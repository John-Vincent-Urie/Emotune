import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:emotune/providers/auth_provider.dart';
import 'package:emotune/screens/auth/login_register_screen.dart';
import 'package:emotune/widgets/emotune_buttons.dart';

/// Pumps an auth screen with the routes it can navigate to. No request is ever
/// made: every case here is decided before the form would reach the network.
Future<void> _pumpAuth(WidgetTester tester, Widget screen) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthProvider>(
      create: (_) => AuthProvider(),
      // The auth screens carry looping decorative animations (the backdrop
      // blobs, button shine, logo pulse) that never settle on their own;
      // reduced motion freezes them so pumpAndSettle can still be used here.
      child: MediaQuery(
        data: const MediaQueryData(disableAnimations: true),
        child: MaterialApp(
          home: screen,
          routes: {
            '/login': (_) => const LoginScreen(),
            '/register': (_) => const RegisterScreen(),
            '/home': (_) => const Scaffold(body: Text('home')),
          },
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

EmoTunePrimaryButton _submitButton(WidgetTester tester) {
  return tester.widget<EmoTunePrimaryButton>(find.byType(EmoTunePrimaryButton));
}

/// The forms are taller than the default 800x600 test viewport, so anything
/// below the fold has to be scrolled to before it can be tapped.
Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Login form', () {
    testWidgets('submit stays disabled until both fields have something',
        (tester) async {
      await _pumpAuth(tester, const LoginScreen());
      expect(_submitButton(tester).onPressed, isNull);

      await tester.enterText(find.byType(TextFormField).first, 'a@b.co');
      await tester.pump();
      expect(_submitButton(tester).onPressed, isNull,
          reason: 'password is still empty');

      await tester.enterText(find.byType(TextFormField).last, 'secret1');
      await tester.pump();
      expect(_submitButton(tester).onPressed, isNotNull);
    });

    testWidgets('a malformed email is caught inline, before any request',
        (tester) async {
      await _pumpAuth(tester, const LoginScreen());
      await tester.enterText(find.byType(TextFormField).first, 'not-an-email');
      await tester.enterText(find.byType(TextFormField).last, 'secret1');
      await tester.pump();

      await tester.tap(find.byType(EmoTunePrimaryButton));
      await tester.pump();

      expect(find.text('Enter a valid email address'), findsOneWidget);
    });

    testWidgets('the password can be revealed and hidden again',
        (tester) async {
      await _pumpAuth(tester, const LoginScreen());

      TextFormField passwordField() =>
          tester.widget<TextFormField>(find.byType(TextFormField).last);
      expect(passwordField().controller, isNotNull);
      expect(find.byTooltip('Show password'), findsOneWidget);

      await tester.tap(find.byTooltip('Show password'));
      await tester.pump();
      expect(find.byTooltip('Hide password'), findsOneWidget);
    });

    testWidgets('offers a way over to registration', (tester) async {
      await _pumpAuth(tester, const LoginScreen());
      expect(find.text("Don't have an account?"), findsOneWidget);

      await _tap(tester, find.text('Create one'));
      expect(find.text('Create your account'), findsOneWidget);
    });
  });

  group('Register form', () {
    Finder fieldAt(int index) => find.byType(TextFormField).at(index);

    Future<void> fillValidForm(WidgetTester tester) async {
      await tester.enterText(fieldAt(0), 'Uri');
      await tester.enterText(fieldAt(1), 'uri@example.com');
      await tester.enterText(fieldAt(2), 'secret123');
      await tester.enterText(fieldAt(3), 'secret123');
      await tester.pump();
    }

    testWidgets('cannot be submitted until the terms are accepted',
        (tester) async {
      await _pumpAuth(tester, const RegisterScreen());
      await fillValidForm(tester);

      expect(_submitButton(tester).onPressed, isNull);
      expect(
        find.text('Agree to the Terms and Privacy Policy to continue.'),
        findsOneWidget,
      );

      await _tap(tester, find.text('I agree to the Terms and Privacy Policy'));

      expect(_submitButton(tester).onPressed, isNotNull);
    });

    testWidgets('a short password is rejected with the server\'s own rule',
        (tester) async {
      await _pumpAuth(tester, const RegisterScreen());
      await tester.enterText(fieldAt(2), 'abc');
      await tester.pump();
      await _tap(tester, find.text('I agree to the Terms and Privacy Policy'));
      await _tap(tester, find.byType(EmoTunePrimaryButton));

      expect(find.text('Use at least 6 characters'), findsOneWidget);
    });

    testWidgets('mismatched passwords are reported on the confirm field',
        (tester) async {
      await _pumpAuth(tester, const RegisterScreen());
      await tester.enterText(fieldAt(2), 'secret123');
      await tester.enterText(fieldAt(3), 'secret124');
      await tester.pump();

      expect(find.text('Passwords do not match'), findsOneWidget);
    });

    testWidgets('password strength is shown while typing', (tester) async {
      await _pumpAuth(tester, const RegisterScreen());

      await tester.enterText(fieldAt(2), 'abc');
      await tester.pump();
      expect(find.text('Too short'), findsOneWidget);

      await tester.enterText(fieldAt(2), 'abcdef');
      await tester.pump();
      expect(find.text('Weak'), findsOneWidget);

      await tester.enterText(fieldAt(2), 'abcdef1234!X');
      await tester.pump();
      expect(find.text('Strong'), findsOneWidget);
    });

    testWidgets('offers a way back to login', (tester) async {
      await _pumpAuth(tester, const RegisterScreen());
      expect(find.text('Already have an account?'), findsOneWidget);

      await _tap(tester, find.text('Log in'));
      expect(find.text('Welcome back'), findsOneWidget);
    });
  });
}
