import 'package:flutter/foundation.dart';

import '../services/api_service.dart';

/// Tracks which tracks are favorited and syncs favorite toggles with the
/// backend. Pulled out of [PlayerProvider] because — unlike playback, queue
/// navigation, and Spotify remote sync, which all read and write the same
/// core playback state — favorites only ever touch the current track's id
/// and their own local set, so they can be a self-contained collaborator.
///
/// It keeps the whole favorite record, not just the id, so the Favorites tab
/// renders straight off this set: a heart tapped anywhere shows up there
/// right away instead of only after the next fetch.
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

  /// Favorite records keyed by track id, in insertion order: newest first,
  /// which is the order the backend lists them in, so an optimistic heart
  /// lands where the server would have put it.
  final Map<String, Map<String, dynamic>> _favoritesById =
      <String, Map<String, dynamic>>{};
  bool _favoritesLoaded = false;
  bool _busy = false;

  /// Bumped by every toggle so an in-flight [refresh] can tell its snapshot
  /// went stale and drop it instead of undoing the toggle.
  int _generation = 0;

  bool get isBusy => _busy;

  /// Whether the first fetch has landed. The Favorites tab waits on this so
  /// an empty set is not mistaken for "no favorites yet".
  bool get isLoaded => _favoritesLoaded;

  /// Every hearted track, newest first, in the backend's favorite shape.
  List<Map<String, dynamic>> get favorites =>
      List<Map<String, dynamic>>.unmodifiable(_favoritesById.values);

  bool isFavorite(Map<String, dynamic>? track) {
    final trackId = track?['id']?.toString().trim() ?? '';
    if (trackId.isEmpty) {
      return false;
    }
    return _favoritesById.containsKey(trackId);
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
    _generation++;
    final wasFavorite = isFavorite(track);
    // Restoring the whole map rolls back either direction of the toggle,
    // including where a removed favorite sat in the list.
    final snapshot = Map<String, Map<String, dynamic>>.from(_favoritesById);
    final normalizedEmotion = emotion?.trim().toLowerCase() ?? '';
    final optimistic = _favoriteFromTrack(
      track,
      trackId: trackId,
      emotion: normalizedEmotion,
    );
    if (wasFavorite) {
      _favoritesById.remove(trackId);
    } else {
      _addFirst(trackId, optimistic);
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

      final payload = Map<String, dynamic>.from(optimistic);
      if (normalizedEmotion.isEmpty) {
        payload.remove('emotion');
      }
      final saved = await ApiService.addFavorite(payload);
      // The saved record carries the server's id, added_at and emotion tag --
      // a favorite hearted before predates this emotion and keeps its own --
      // so swap the optimistic stand-in for it.
      if (_favoritesById.containsKey(trackId)) {
        _addFirst(trackId, Map<String, dynamic>.from(saved));
      }
      onError(null);
      onChanged();
      return true;
    } catch (_) {
      _favoritesById
        ..clear()
        ..addAll(snapshot);
      onError('Could not update favorites right now.');
      onChanged();
      return null;
    } finally {
      _busy = false;
    }
  }

  /// The fetch already on the wire, if any. App start, the Favorites tab and
  /// every loadPlaylist all ask for a refresh, and on landing they fired
  /// within the same second; joining the open request keeps that to one.
  Future<void>? _inFlightRefresh;

  Future<void> refresh() {
    return _inFlightRefresh ??=
        _fetch().whenComplete(() => _inFlightRefresh = null);
  }

  Future<void> _fetch() async {
    final generation = _generation;
    try {
      final favorites = await ApiService.getFavorites();
      if (generation != _generation) {
        // A toggle landed while this fetch was in flight, so its result is
        // newer than what the server just told us.
        return;
      }
      _favoritesById
        ..clear()
        ..addEntries(
          favorites
              .whereType<Map>()
              .map(_favoriteEntry)
              .whereType<MapEntry<String, Map<String, dynamic>>>(),
        );
      _favoritesLoaded = true;
      onChanged();
    } catch (_) {
      if (!_favoritesLoaded) {
        _favoritesById.clear();
      }
    }
  }

  MapEntry<String, Map<String, dynamic>>? _favoriteEntry(Map favorite) {
    final trackId = favorite['spotify_track_id']?.toString().trim() ?? '';
    if (trackId.isEmpty) {
      return null;
    }
    return MapEntry(trackId, Map<String, dynamic>.from(favorite));
  }

  /// Puts [trackId] at the front, so a fresh heart shows up at the top of the
  /// Favorites tab the way the backend's newest-first ordering would place it.
  void _addFirst(String trackId, Map<String, dynamic> favorite) {
    final rest = Map<String, Map<String, dynamic>>.from(_favoritesById)
      ..remove(trackId);
    _favoritesById
      ..clear()
      ..[trackId] = favorite
      ..addAll(rest);
  }

  /// A player track map (`id`/`name`/`artist`) in the backend's favorite
  /// shape (`spotify_track_id`/`track_name`/`artist_name`).
  Map<String, dynamic> _favoriteFromTrack(
    Map<String, dynamic> track, {
    required String trackId,
    required String emotion,
  }) {
    return {
      'spotify_track_id': trackId,
      'track_name': track['name'],
      'artist_name': track['artist'],
      'album_name': track['album'] ?? '',
      'album_image': track['image'] ?? '',
      'preview_url': track['preview_url'],
      'duration_ms': track['duration_ms'] ?? 0,
      'emotion': emotion,
    };
  }
}
