// White-box tests for the player's stateful collaborators: FavoritesManager
// (optimistic toggle, rollback, stale refresh) and SpotifyAvailabilityTracker
// (block / unblock rules and the 5-minute cache). The backend is replaced by
// a MockClient so each branch can be forced. IDs match the documentation.
import 'dart:async';
import 'dart:convert';

import 'package:emotune/providers/favorites_manager.dart';
import 'package:emotune/providers/spotify_availability_tracker.dart';
import 'package:emotune/services/api_service.dart';
import 'package:emotune/services/spotify_remote_service.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response jsonResponse(Object body, [int status = 200]) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({
      'resolved_api_base_url': 'http://emotune.test/api',
      'access_token': 'token',
      'refresh_token': 'refresh',
    });
  });

  tearDown(() {
    ApiService.httpClient = http.Client();
    debugDefaultTargetPlatformOverride = null;
  });

  group('FavoritesManager', () {
    late List<String?> errors;
    late int changes;
    late FavoritesManager manager;

    setUp(() {
      errors = [];
      changes = 0;
      manager = FavoritesManager(
        onError: errors.add,
        onChanged: () => changes++,
      );
    });

    const song = {'id': 't1', 'name': 'Song', 'artist': 'A'};

    test('WB-FAV-01 invalid input is ignored without a request', () async {
      var calls = 0;
      ApiService.httpClient = MockClient((_) async {
        calls++;
        return jsonResponse({});
      });
      expect(await manager.toggleForTrack(null), isNull);
      expect(await manager.toggleForTrack({'id': ' '}), isNull);
      expect(calls, 0);
    });

    test('WB-FAV-02 non-track items are refused with a message', () async {
      final result = await manager.toggleForTrack(
        {'id': 'p1', 'item_type': 'playlist'},
      );
      expect(result, isNull);
      expect(errors.last, contains('Only individual songs'));
    });

    test('WB-FAV-03 add sends the emotion and stores the saved record',
        () async {
      late Map<String, dynamic> sent;
      ApiService.httpClient = MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse({...sent, 'id': 99}, 201);
      });
      expect(await manager.toggleForTrack(song, emotion: ' Sad '), isTrue);
      expect(sent['emotion'], 'sad');
      expect(manager.isFavorite(song), isTrue);
      expect(manager.favorites.single['id'], 99);
    });

    test('WB-FAV-04 add without emotion leaves the field out', () async {
      late Map<String, dynamic> sent;
      ApiService.httpClient = MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse(sent, 201);
      });
      await manager.toggleForTrack(song);
      expect(sent.containsKey('emotion'), isFalse);
    });

    test('WB-FAV-05 second toggle removes the favorite', () async {
      ApiService.httpClient = MockClient((request) async {
        if (request.method == 'DELETE') return http.Response('', 204);
        return jsonResponse(jsonDecode(request.body) as Object, 201);
      });
      await manager.toggleForTrack(song);
      expect(await manager.toggleForTrack(song), isFalse);
      expect(manager.isFavorite(song), isFalse);
    });

    test('WB-FAV-06 a server error rolls the optimistic change back',
        () async {
      ApiService.httpClient =
          MockClient((_) async => jsonResponse({'detail': 'boom'}, 500));
      expect(await manager.toggleForTrack(song), isNull);
      expect(manager.isFavorite(song), isFalse);
      expect(errors.last, 'Could not update favorites right now.');
    });

    test('WB-FAV-07 refresh loads records and skips ones without an id',
        () async {
      ApiService.httpClient = MockClient((_) async => jsonResponse([
            {'spotify_track_id': 'a'},
            {'spotify_track_id': ''},
            'junk',
          ]));
      await manager.refresh();
      expect(manager.isLoaded, isTrue);
      expect(manager.favorites.length, 1);
    });

    test('WB-FAV-08 concurrent refreshes share one request', () async {
      var calls = 0;
      ApiService.httpClient = MockClient((_) async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 10));
        return jsonResponse([]);
      });
      await Future.wait([manager.refresh(), manager.refresh()]);
      expect(calls, 1);
    });

    test('WB-FAV-09 a refresh that lands after a toggle is discarded',
        () async {
      final listGate = Completer<void>();
      ApiService.httpClient = MockClient((request) async {
        if (request.method == 'GET') {
          await listGate.future;
          return jsonResponse([]);
        }
        return jsonResponse(jsonDecode(request.body) as Object, 201);
      });
      final pending = manager.refresh();
      await manager.toggleForTrack(song);
      listGate.complete();
      await pending;
      expect(manager.isFavorite(song), isTrue);
    });
  });

  group('SpotifyAvailabilityTracker', () {
    late int changes;
    late int calls;
    late SpotifyAvailabilityTracker tracker;

    void serveStatus(Map<String, dynamic> status) {
      ApiService.httpClient = MockClient((_) async {
        calls++;
        return jsonResponse(status);
      });
    }

    setUp(() {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      changes = 0;
      calls = 0;
      tracker = SpotifyAvailabilityTracker(
        spotifyRemote: SpotifyRemoteService.instance,
        onChanged: () => changes++,
      );
    });

    test('WB-SPA-01 not supported platforms never call the backend',
        () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      serveStatus({});
      await tracker.ensureChecked();
      expect(calls, 0);
    });

    test('WB-SPA-02 allowlist problem blocks with the server message',
        () async {
      serveStatus({
        'spotify_connected': true,
        'recommended_action': 'Ask to be added',
        'account': {'developer_allowlist_required': true},
      });
      await tracker.ensureChecked();
      expect(tracker.isBlocked, isTrue);
      expect(tracker.blockedReason, 'Ask to be added');
    });

    test('WB-SPA-03 a known non-Premium account is blocked', () async {
      serveStatus({
        'spotify_connected': true,
        'account': {'premium_status_known': true, 'has_premium': false},
      });
      await tracker.ensureChecked();
      expect(tracker.blockedReason, contains('Premium'));
    });

    test('WB-SPA-04 a disconnected backend link is not a block', () async {
      tracker.markBlocked('old');
      serveStatus({'spotify_connected': false});
      await tracker.ensureChecked();
      expect(tracker.isBlocked, isFalse);
    });

    test('WB-SPA-05 result is cached; force bypasses the cache', () async {
      serveStatus({'spotify_connected': true, 'account': {}});
      await tracker.ensureChecked();
      await tracker.ensureChecked();
      expect(calls, 1);
      await tracker.retry();
      expect(calls, 2);
    });

    test('WB-SPA-06 a failed check keeps the previous state', () async {
      tracker.markBlocked('kept');
      ApiService.httpClient =
          MockClient((_) async => jsonResponse({'detail': 'x'}, 500));
      await tracker.ensureChecked();
      expect(tracker.blockedReason, 'kept');
    });

    test('WB-SPA-07 markBlocked notifies only on a change', () {
      tracker.markBlocked('  ');
      expect(tracker.blockedReason, contains('unavailable'));
      tracker.markBlocked('  ');
      expect(changes, 1);
    });
  });
}
