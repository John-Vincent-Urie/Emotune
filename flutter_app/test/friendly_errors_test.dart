import 'dart:convert';

import 'package:emotune/providers/auth_provider.dart';
import 'package:emotune/services/api_service.dart';
import 'package:emotune/screens/auth/welcome_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  http.Response json(Object body, int status, [Map<String, String>? headers]) =>
      http.Response(
        jsonEncode(body),
        status,
        headers: {'content-type': 'application/json', ...?headers},
      );

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'resolved_api_base_url': 'http://emotune.test/api',
    });
  });

  tearDown(() => ApiService.httpClient = http.Client());

  group('throttled responses', () {
    Future<ApiException> throttled(http.Response response) async {
      ApiService.httpClient = MockClient((_) async => response);
      try {
        await ApiService.login('qa@example.com', 'secret123');
      } on ApiException catch (e) {
        return e;
      }
      fail('expected an ApiException');
    }

    test('drop DRF wording but keep the wait', () async {
      final e = await throttled(json(
        {'detail': 'Request was throttled. Expected available in 57 seconds.'},
        429,
      ));
      expect(e.statusCode, 429);
      expect(e.message, isNot(contains('throttled')));
      expect(e.message, contains('57 seconds'));
    });

    test('round long waits up to minutes', () async {
      final e = await throttled(json({}, 429, {'retry-after': '125'}));
      expect(e.message, contains('3 minutes'));
    });

    test('still read when no wait is given', () async {
      final e = await throttled(json({}, 429));
      expect(e.message, contains('wait a moment'));
    });
  });

  test('every failed password rule is shown, not just the first', () async {
    ApiService.httpClient = MockClient((_) async => json({
          'password': [
            'This password is too short. It must contain at least 8 characters.',
            'This password is entirely numeric.',
          ],
        }, 400));
    try {
      await ApiService.register('Uri', 'qa@example.com', '1234567',
          acceptTerms: true);
      fail('expected an ApiException');
    } on ApiException catch (e) {
      expect(e.message, contains('at least 8 characters'));
      expect(e.message, contains('entirely numeric'));
    }
  });

  test('wrong credentials say what to check', () async {
    ApiService.httpClient = MockClient(
      (_) async => json({'error': 'Invalid credentials'}, 401),
    );
    final auth = AuthProvider();

    expect(await auth.login('qa@example.com', 'nope'), isFalse);
    expect(auth.error, 'Wrong email or password.');
  });

  testWidgets('welcome buttons are announced once, not twice',
      (tester) async {
    GoogleFonts.config.allowRuntimeFetching = false;
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(const MediaQuery(
      data: MediaQueryData(disableAnimations: true),
      child: MaterialApp(home: WelcomeScreen()),
    ));
    await tester.pumpAndSettle();

    final node = tester.getSemantics(find.bySemanticsLabel('Login'));
    expect(node.label, 'Login');
    handle.dispose();
  });
}
