import 'package:flutter_test/flutter_test.dart';

import 'package:emotune/controllers/recommendation_session_controller.dart';
import 'package:emotune/providers/player_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const session = RecommendationSessionController();

  Map<String, dynamic> track(String id, {String? previewUrl}) {
    return <String, dynamic>{
      'id': id,
      'name': 'Song $id',
      'artist': 'Artist $id',
      'uri': 'spotify:track:$id',
      if (previewUrl != null) 'preview_url': previewUrl,
    };
  }

  group('playlistForSelection / indexOfSelection', () {
    test('resolves the tapped track after unidentified rows are filtered out',
        () {
      // normalizeTrackList drops rows carrying no identifier at all, so the
      // row index the screen tapped no longer addresses the same track.
      final tracks = <Map<String, dynamic>>[
        <String, dynamic>{'name': 'No id, uri, url or preview'},
        track('aaa'),
        track('bbb'),
      ];
      final selected = track('bbb');

      final playlist = session.playlistForSelection(tracks, selected);

      expect(playlist.length, 2);
      expect(session.indexOfSelection(playlist, selected), 1);
      expect(playlist[session.indexOfSelection(playlist, selected)]['id'],
          'bbb');
    });

    test('resolves the last track instead of running off the end', () {
      final tracks = <Map<String, dynamic>>[
        <String, dynamic>{'name': 'Unidentified'},
        <String, dynamic>{'name': 'Unidentified'},
        track('ccc'),
      ];
      final selected = track('ccc');

      final playlist = session.playlistForSelection(tracks, selected);

      expect(playlist.length, 1);
      expect(session.indexOfSelection(playlist, selected), 0);
    });

    test('keeps every index when nothing is filtered out', () {
      final tracks = [track('aaa'), track('bbb'), track('ccc')];

      for (var index = 0; index < tracks.length; index += 1) {
        final playlist = session.playlistForSelection(tracks, tracks[index]);
        expect(playlist.length, 3);
        expect(session.indexOfSelection(playlist, tracks[index]), index);
      }
    });

    test('falls back to the single-track playlist when the pick is missing',
        () {
      final tracks = [track('aaa'), track('bbb')];
      final selected = track('zzz');

      final playlist = session.playlistForSelection(tracks, selected);

      expect(playlist.length, 1);
      expect(playlist.single['id'], 'zzz');
      expect(session.indexOfSelection(playlist, selected), 0);
    });

    test('matches a selection that only carries a spotify_url', () {
      final tracks = [track('aaa'), track('bbb')];
      final selected = <String, dynamic>{
        'name': 'Song bbb',
        'spotify_url': 'https://open.spotify.com/track/bbb',
      };

      final playlist = session.playlistForSelection(tracks, selected);

      expect(playlist.length, 2);
      expect(session.indexOfSelection(playlist, selected), 1);
    });
  });

  group('songs Spotify could not resolve', () {
    Map<String, dynamic> unresolved(int n) => <String, dynamic>{
          'id': 'music-doc-unresolved-$n',
          'name': 'Missing $n',
          'artist': 'Someone',
          'uri': '',
          'spotify_url': 'https://open.spotify.com/search/Missing%20$n',
          'playable': false,
          'is_music_doc_pick': true,
        };

    test('stay in the visible list without a fake Spotify uri', () {
      final shown = PlayerProvider.normalizeTrackList([
        unresolved(1),
        track('aaa'),
      ]);
      expect(shown, hasLength(2));
      expect(shown.first['uri'], isEmpty);
      expect(shown.first['spotify_url'], contains('/search/'));
    });

    test('are left out of the queue, so the tapped index still lines up', () {
      final tracks = PlayerProvider.normalizeTrackList([
        unresolved(1),
        track('aaa'),
        unresolved(2),
        track('bbb'),
      ]);
      final selected = PlayerProvider.normalizeTrack(track('bbb'));
      final playlist = session.playlistForSelection(tracks, selected);

      expect(playlist.map((t) => t['id']), ['aaa', 'bbb']);
      expect(session.indexOfSelection(playlist, selected), 1);
    });
  });

  test('an unmatched song with uri null stays unplayable', () {
    final shown = PlayerProvider.normalizeTrackList([
      <String, dynamic>{
        'id': 'song-42',
        'name': 'Unmatched',
        'artist': 'Someone',
        'uri': null,
        'spotify_url': 'https://open.spotify.com/search/Unmatched%20Someone',
        'playable': false,
      },
    ]);
    expect(shown.single['uri'], isEmpty);
    expect(PlayerProvider.isPlayable(shown.single), isFalse);
  });
}
