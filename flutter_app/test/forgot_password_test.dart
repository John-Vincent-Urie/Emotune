import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:emotune/providers/auth_provider.dart';
import 'package:emotune/screens/auth/login_register_screen.dart';
import 'package:emotune/services/api_service.dart';
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

  group('wrong reset code', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({
        'resolved_api_base_url': 'http://emotune.test/api',
      });
      ApiService.httpClient = MockClient((request) async {
        if (request.url.path.contains('verify')) {
          return http.Response(
            jsonEncode({'error': 'That code is not valid.'}),
            400,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({'message': 'sent'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
    });

    tearDown(() => ApiService.httpClient = http.Client());

    testWidgets('clears the boxes and still says why', (tester) async {
      await _pumpReset(tester, initialEmail: 'robin@example.com');
      await tester.tap(find.text('Send code'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField).first, '111111');
      await tester.pumpAndSettle();

      expect(find.text('That code is not valid.'), findsOneWidget);
      final code = tester.widget<TextField>(find.byType(TextField).first);
      expect(code.controller!.text, isEmpty);
    });
  });
}
