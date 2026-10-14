// White-box tests for the app's pure helper logic. Each test drives one
// branch of the code under test; the IDs (WB-FL-nn) match the white-box
// testing documentation.
import 'package:emotune/controllers/recommendation_session_controller.dart';
import 'package:emotune/providers/player_track_utils.dart';
import 'package:emotune/services/support_contacts.dart';
import 'package:emotune/theme/emotion_names.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('normalizeTrack (player_track_utils.dart)', () {
    test('WB-FL-01 builds uri and url from a bare id', () {
      final track = normalizeTrack({'id': 'abc'});
      expect(track['uri'], 'spotify:track:abc');
      expect(track['spotify_url'], 'https://open.spotify.com/track/abc');
      expect(track['item_type'], 'track');
    });

    test('WB-FL-02 reads type and id from a spotify: uri', () {
      final track = normalizeTrack({'uri': 'spotify:playlist:p1'});
      expect(track['item_type'], 'playlist');
      expect(track['id'], 'p1');
    });

    test('WB-FL-03 reads type and id from an open.spotify.com url', () {
      final track =
          normalizeTrack({'spotify_url': 'https://open.spotify.com/album/x9'});
      expect(track['item_type'], 'album');
      expect(track['uri'], 'spotify:album:x9');
    });

    test('WB-FL-04 ignores urls from other hosts', () {
      final track =
          normalizeTrack({'spotify_url': 'https://example.com/track/zz'});
      expect(track['uri'], '');
      expect(track['id'], '');
    });

    test('WB-FL-05 an unresolved music.md song is never given a uri', () {
      final track = normalizeTrack(
        {'id': 'music-doc-unresolved-3', 'playable': false},
      );
      expect(track['uri'], '');
      expect(track['spotify_url'], '');
      expect(isPlayable(track), isFalse);
    });

    test('WB-FL-06 an unsupported item type does not get a uri', () {
      final track = normalizeTrack({'id': 'q', 'item_type': 'audiobook'});
      expect(track['uri'], '');
    });
  });

  group('track list helpers', () {
    test('WB-FL-07 normalizeTrackList keeps playable, preview and unresolved',
        () {
      final list = normalizeTrackList([
        'not a map',
        {'id': 'a'},
        {'preview_url': 'http://p'},
        {'id': 'u', 'playable': false},
        {'name': 'nothing playable'},
      ]);
      expect(list.length, 3);
    });

    test('WB-FL-08 mergeTrackLists drops duplicates across lists', () {
      final merged = mergeTrackLists(
        [
          {'id': 'a'},
          {'id': 'b'},
        ],
        [
          {'uri': 'spotify:track:a'},
          {'id': 'c'},
          {'name': 'no identity'},
        ],
      );
      expect(merged.map((t) => t['id']), ['a', 'b', 'c']);
    });

    test('WB-FL-09 trackIdentity falls back to uri then url', () {
      expect(trackIdentity({'id': 'a'}), 'track:a');
      expect(trackIdentity({'name': 'x'}), '');
    });

    test('WB-FL-10 container detection', () {
      expect(isContainerType(' Playlist '), isTrue);
      expect(isContainerType('collection'), isTrue);
      expect(isContainerType('track'), isFalse);
      expect(isContainerItem({'item_type': 'album'}), isTrue);
      expect(isContainerItem({}), isFalse);
    });
  });

  group('small converters', () {
    test('WB-FL-11 safeInt handles int, double, string and junk', () {
      expect(safeInt(5), 5);
      expect(safeInt(5.9), 5);
      expect(safeInt('12'), 12);
      expect(safeInt('x', 7), 7);
      expect(safeInt(null), 0);
    });

    test('WB-FL-12 normalizeObjectMap only accepts maps', () {
      expect(normalizeObjectMap({'a': 1}), {'a': 1});
      expect(normalizeObjectMap('x'), isNull);
    });

    test('WB-FL-13 normalizeOutcomeMode defaults to match_mood', () {
      expect(normalizeOutcomeMode(' CALM_ME_DOWN '), 'calm_me_down');
      expect(normalizeOutcomeMode('other'), 'match_mood');
      expect(normalizeOutcomeMode(null), 'match_mood');
    });

    test('WB-FL-14 composeSpotifyControlMessage priority order', () {
      expect(
        composeSpotifyControlMessage(
          {
            'recommended_action': 'Reconnect',
            'spotify_error': {'error': 'e'},
          },
          defaultMessage: 'd',
        ),
        'Reconnect',
      );
      expect(
        composeSpotifyControlMessage(
          {
            'spotify_error': {'error': 'Premium needed'},
          },
          defaultMessage: 'd',
        ),
        'Premium needed',
      );
      expect(
        composeSpotifyControlMessage(
          {'blocking_issue': 'no_device'},
          defaultMessage: 'd',
        ),
        contains('no_device'),
      );
      expect(composeSpotifyControlMessage({}, defaultMessage: 'd'), 'd');
    });
  });

  group('emotionDisplayName (emotion_names.dart)', () {
    test('WB-FL-15 server name wins over the local table', () {
      expect(emotionDisplayName('fear', serverDisplayName: ' Afraid '),
          'Afraid');
    });

    test('WB-FL-16 therapist names replace model keys', () {
      expect(emotionDisplayName(' FEAR '), 'Scared');
      expect(emotionDisplayName('motivational'), 'Motivated');
    });

    test('WB-FL-17 unknown keys are capitalised, blanks stay blank', () {
      expect(emotionDisplayName('bored'), 'Bored');
      expect(emotionDisplayName(null), '');
      expect(emotionDisplayName('  '), '');
    });
  });

  group('support contacts (support_contacts.dart)', () {
    test('WB-FL-18 server contacts are used when they have names', () {
      final contacts = supportContactsOrBundled([
        {'name': 'Clinic', 'phone': '123'},
        {'name': '  '},
        'junk',
      ]);
      expect(contacts.map((c) => c['name']), ['Clinic']);
    });

    test('WB-FL-19 bundled list is the fallback, never empty', () {
      expect(supportContactsOrBundled(null), isNotEmpty);
      expect(supportContactsOrBundled([
        {'name': ''},
      ]).first['name'], startsWith('Music Cares'));
    });

    test('WB-FL-20 bundled list is a copy, not the constant', () {
      final contacts = supportContactsOrBundled(const []);
      contacts.first['name'] = 'changed';
      expect(kBundledSupportContacts.first['name'], isNot('changed'));
    });

    test('WB-FL-21 dialUri strips formatting', () {
      expect(dialUri('+63 (917) 325-5789').toString(), 'tel:+639173255789');
    });
  });

  group('RecommendationSessionController', () {
    const controller = RecommendationSessionController();

    test('WB-FL-22 historyIdFromResult accepts int, double and string', () {
      expect(controller.historyIdFromResult({'history_id': 4}), 4);
      expect(controller.historyIdFromResult({'history_id': 4.0}), 4);
      expect(controller.historyIdFromResult({'history_id': '9'}), 9);
      expect(controller.historyIdFromResult({'history_id': 'x'}), isNull);
      expect(controller.historyIdFromResult(null), isNull);
    });

    test('WB-FL-23 sessionPlanFromResult only accepts a map', () {
      expect(
        controller.sessionPlanFromResult({
          'session_plan': {'steps': 3},
        }),
        {'steps': 3},
      );
      expect(controller.sessionPlanFromResult({'session_plan': 'x'}), isNull);
    });

    test('WB-FL-24 playback emotion: target, then detected, then default',
        () {
      expect(
        controller.playbackEmotionFromResult(
          {'recommendation_target_emotion': 'calm', 'emotion': 'sad'},
        ),
        'calm',
      );
      expect(controller.playbackEmotionFromResult({'emotion': 'sad'}), 'sad');
      expect(
        controller.playbackEmotionFromResult(null, defaultEmotion: 'happy'),
        'happy',
      );
    });
  });
}
