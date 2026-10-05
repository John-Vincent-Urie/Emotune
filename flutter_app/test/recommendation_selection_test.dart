import 'package:flutter_test/flutter_test.dart';

import 'package:emotune/controllers/recommendation_session_controller.dart';

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
}
