import 'package:flutter/foundation.dart';

import '../services/api_service.dart';

/// Tracks which tracks are favorited and syncs favorite toggles with the
/// backend. Pulled out of [PlayerProvider] because — unlike playback, queue
/// navigation, and Spotify remote sync, which all read and write the same
/// core playback state — favorites only ever touch the current track's id
/// and their own local set, so they can be a self-contained collaborator.
///
/// [onError] mirrors [PlayerProvider]'s shared `errorMessage` field (a
/// favorites failure surfaces through the same error banner as a playback
/// failure), and [onChanged] is [PlayerProvider.notifyListeners].
class FavoritesManager {
  FavoritesManager({
    required this.onError,
    required this.onChanged,
  });

  final void Function(String? message) onError;
  final VoidCallback onChanged;

  final Set<String> _favoriteTrackIds = <String>{};
  bool _favoritesLoaded = false;
  bool _busy = false;

  bool get isBusy => _busy;

  bool isFavorite(Map<String, dynamic>? track) {
    final trackId = track?['id']?.toString().trim() ?? '';
    if (trackId.isEmpty) {
      return false;
    }
    return _favoriteTrackIds.contains(trackId);
  }

  /// [emotion] is the emotion the playlist was built for. It is stored with
  /// the favorite so the "More familiar" taste control can replay what the user
  /// hearted the next time that emotion comes up.
  Future<bool?> toggleForTrack(
    Map<String, dynamic>? track, {
    String? emotion,
  }) async {
    final trackId = track?['id']?.toString().trim() ?? '';
    final itemType =
        track?['item_type']?.toString().trim().toLowerCase() ?? 'track';
    if (track == null || trackId.isEmpty || _busy) {
      return null;
    }
    if (itemType != 'track') {
      onError('Only individual songs can be added to favorites.');
      onChanged();
      return null;
    }

    _busy = true;
    final wasFavorite = isFavorite(track);
    if (wasFavorite) {
      _favoriteTrackIds.remove(trackId);
    } else {
      _favoriteTrackIds.add(trackId);
    }
    onError(null);
    onChanged();
    try {
      if (wasFavorite) {
        await ApiService.removeFavorite(trackId);
        onError(null);
        onChanged();
        return false;
      }

      final normalizedEmotion = emotion?.trim().toLowerCase() ?? '';
      await ApiService.addFavorite({
        'spotify_track_id': trackId,
        'track_name': track['name'],
        'artist_name': track['artist'],
        'album_name': track['album'] ?? '',
        'album_image': track['image'] ?? '',
        'preview_url': track['preview_url'],
        'duration_ms': track['duration_ms'] ?? 0,
        if (normalizedEmotion.isNotEmpty) 'emotion': normalizedEmotion,
      });
      onError(null);
      onChanged();
      return true;
    } catch (_) {
      if (wasFavorite) {
        _favoriteTrackIds.add(trackId);
      } else {
        _favoriteTrackIds.remove(trackId);
      }
      onError('Could not update favorites right now.');
      onChanged();
      return null;
    } finally {
      _busy = false;
    }
  }

  Future<void> refresh() async {
    try {
      final favorites = await ApiService.getFavorites();
      _favoriteTrackIds
        ..clear()
        ..addAll(
          favorites
              .whereType<Map>()
              .map((favorite) =>
                  favorite['spotify_track_id']?.toString().trim() ?? '')
              .where((trackId) => trackId.isNotEmpty),
        );
      _favoritesLoaded = true;
      onChanged();
    } catch (_) {
      if (!_favoritesLoaded) {
        _favoriteTrackIds.clear();
      }
    }
  }
}
