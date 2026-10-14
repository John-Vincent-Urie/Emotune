import 'dart:convert';

import 'package:emotune/services/api_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  late int refreshCalls;
  late int expiredCalls;

  http.Response json(Object body, int status) => http.Response(
        jsonEncode(body),
        status,
        headers: {'content-type': 'application/json'},
      );

  /// Accepts only the token named [validToken]; the refresh endpoint answers
  /// with [refreshStatus] after a short delay so concurrent callers overlap.
  void serve({required String validToken, int refreshStatus = 200}) {
    ApiService.httpClient = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/users/token/refresh/')) {
        refreshCalls++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        if (refreshStatus != 200) {
          return json({'detail': 'Token is invalid or expired'}, refreshStatus);
        }
        return json({'access': 'new-access', 'refresh': 'new-refresh'}, 200);
      }
      if (path.endsWith('/users/login/')) {
        return json({'detail': 'No active account'}, 401);
      }
      if (request.headers['Authorization'] == 'Bearer $validToken') {
        return json({'id': 1, 'username': 'qa'}, 200);
      }
      return json({'detail': 'Given token not valid'}, 401);
    });
  }

  setUp(() {
    refreshCalls = 0;
    expiredCalls = 0;
    SharedPreferences.setMockInitialValues({
      // A persisted base URL skips the Android reachability probe.
      'resolved_api_base_url': 'http://emotune.test/api',
      'access_token': 'expired-access',
      'refresh_token': 'old-refresh',
    });
    ApiService.onSessionExpired = () async => expiredCalls++;
  });

  tearDown(() {
    ApiService.onSessionExpired = null;
    ApiService.httpClient = http.Client();
  });

  test('concurrent 401s share one refresh and each request is replayed',
      () async {
    serve(validToken: 'new-access');

    final results = await Future.wait(
      List.generate(4, (_) => ApiService.getProfile()),
    );

    expect(results.map((r) => r['username']), everyElement('qa'));
    expect(refreshCalls, 1);
    expect(expiredCalls, 0);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('access_token'), 'new-access');
    expect(prefs.getString('refresh_token'), 'new-refresh');
  });

  test('a rejected refresh clears the session once and does not loop',
      () async {
    serve(validToken: 'never-issued', refreshStatus: 401);

    final results = await Future.wait(
      List.generate(3, (_) async {
        try {
          await ApiService.getProfile();
          return null;
        } on ApiException catch (e) {
          return e.statusCode;
        }
      }),
    );

    expect(results, everyElement(401));
    expect(refreshCalls, 1);
    expect(expiredCalls, 1);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('access_token'), isNull);
    expect(prefs.getString('refresh_token'), isNull);
  });

  test('a backend error during refresh keeps the session', () async {
    serve(validToken: 'never-issued', refreshStatus: 503);

    await expectLater(
      ApiService.getProfile(),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 401)),
    );

    expect(refreshCalls, 1);
    expect(expiredCalls, 0);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('refresh_token'), 'old-refresh');
  });

  test('a 401 from login is an answer, not a reason to refresh', () async {
    serve(validToken: 'new-access');

    try {
      await ApiService.login('qa@example.com', 'wrong-password');
    } catch (_) {
      // Whether login throws or returns the error is not under test here.
    }

    expect(refreshCalls, 0);
    expect(expiredCalls, 0);
  });
}
