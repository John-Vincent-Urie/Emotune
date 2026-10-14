import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/player_provider.dart';
import '../services/spotify_remote_service.dart';
import '../screens/home/full_player_screen.dart';

/// Shared recommendation/playback-session logic used by both the home chat
/// screen and the recommendations screen. Holds no screen state itself —
/// every method takes the data it needs as parameters and returns a result,
/// so each screen keeps owning its own `_tracks`/`_lastResult` state.
class RecommendationSessionController {
  const RecommendationSessionController();

  int? historyIdFromResult(Map<String, dynamic>? result) {
    final historyId = result?['history_id'];
    if (historyId is int) {
      return historyId;
    }
    if (historyId is num) {
      return historyId.toInt();
    }
    return int.tryParse(historyId?.toString() ?? '');
  }

  Map<String, dynamic>? sessionPlanFromResult(Map<String, dynamic>? result) {
    final raw = result?['session_plan'];
    if (raw is! Map) {
      return null;
    }
    return Map<String, dynamic>.from(raw);
  }

  /// [defaultEmotion] is the screen-specific fallback used when [result]
  /// carries no emotion at all (home uses 'mixed'; the recommendations
  /// screen uses the currently-selected emotion tab, falling back to
  /// 'mixed').
  String playbackEmotionFromResult(
    Map<String, dynamic>? result, {
    String defaultEmotion = 'mixed',
  }) {
    final recommendationTarget =
        result?['recommendation_target_emotion']?.toString().trim() ?? '';
    if (recommendationTarget.isNotEmpty) {
      return recommendationTarget;
    }

    final detectedEmotion = result?['emotion']?.toString().trim() ?? '';
    if (detectedEmotion.isNotEmpty) {
      return detectedEmotion;
    }

    return defaultEmotion;
  }

  void loadPlaylistIntoPlayer(
    PlayerProvider player,
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic>? result,
    {
    String defaultEmotion = 'mixed',
    String? fallbackEmotion,
    bool autoplay = false,
  }) {
    final playbackEmotion =
        playbackEmotionFromResult(result, defaultEmotion: defaultEmotion);
    player.loadPlaylist(
      tracks,
      playbackEmotion == 'mixed' && fallbackEmotion != null
          ? fallbackEmotion
          : playbackEmotion,
      historyId: historyIdFromResult(result ?? const <String, dynamic>{}),
      autoplay: autoplay,
      sessionPlan: sessionPlanFromResult(result),
      outcomeMode: result?['outcome_mode']?.toString(),
      outcomeLabel: result?['outcome_label']?.toString(),
      outcomeDescription: result?['outcome_description']?.toString(),
    );
  }

  List<Map<String, dynamic>> playlistForSelection(
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic> selectedTrack,
  ) {
    // The same filter PlayerProvider.loadPlaylist applies, so the index
    // resolved here addresses the queue the player actually holds.
    final playlist = PlayerProvider.normalizeTrackList(tracks)
        .where(PlayerProvider.isPlayable)
        .toList();
    // Compare against a normalized copy: every entry in [playlist] has had its
    // id and uri filled in from whichever identifier it arrived with, so a
    // selection still carrying only a spotify_url would never match a raw
    // id/uri comparison and would be treated as absent from its own list.
    final selectedIdentity = PlayerProvider.trackIdentityOf(selectedTrack);
    final containsSelection = selectedIdentity.isNotEmpty &&
        playlist.any(
          (track) => PlayerProvider.trackIdentityOf(track) == selectedIdentity,
        );
    if (containsSelection && playlist.isNotEmpty) {
      return playlist;
    }
    return [selectedTrack];
  }

  /// Where [selectedTrack] sits in the playlist that will actually be loaded.
  ///
  /// The row index a screen tapped indexes its own `_tracks`, not the list
  /// [playlistForSelection] returns: that one is filtered (entries carrying no
  /// identifier at all are dropped) and may be replaced outright by a
  /// single-track list. Re-resolving by identity keeps the tapped song and the
  /// index that starts playback in step however the list was reshaped.
  int indexOfSelection(
    List<Map<String, dynamic>> playlist,
    Map<String, dynamic> selectedTrack,
  ) {
    final selectedIdentity = PlayerProvider.trackIdentityOf(selectedTrack);
    if (selectedIdentity.isEmpty) {
      return 0;
    }
    final matchedIndex = playlist.indexWhere(
      (track) => PlayerProvider.trackIdentityOf(track) == selectedIdentity,
    );
    return matchedIndex >= 0 ? matchedIndex : 0;
  }

  Future<void> openPlayer(BuildContext context) async {
    if (!context.mounted) {
      return;
    }
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const FullPlayerScreen(),
    );
  }

  /// Plays [selectedTrack] (already normalized by the caller via
  /// `PlayerProvider.normalizeTrack`), preferring Spotify remote playback
  /// when available, then opens the full player sheet.
  Future<void> playTrackFromList(
    BuildContext context, {
    required List<Map<String, dynamic>> tracks,
    required Map<String, dynamic> selectedTrack,
    required Map<String, dynamic>? lastResult,
    String defaultEmotion = 'mixed',
  }) async {
    final previewUrl = selectedTrack['preview_url']?.toString().trim() ?? '';
    final spotifyUri = selectedTrack['uri']?.toString().trim() ?? '';
    final spotifyUrl = selectedTrack['spotify_url']?.toString().trim() ?? '';

    // A music.md song Spotify could not resolve has nothing to play; its card
    // offers "Open in Spotify", which opens a search for it.
    if (!PlayerProvider.isPlayable(selectedTrack)) {
      if (spotifyUrl.isNotEmpty) {
        await launchUrl(
          Uri.parse(spotifyUrl),
          mode: LaunchMode.externalApplication,
        );
      }
      return;
    }

    final trackList = playlistForSelection(tracks, selectedTrack);
    final hasSpotifyTarget = spotifyUri.isNotEmpty || spotifyUrl.isNotEmpty;
    final playbackEmotion =
        playbackEmotionFromResult(lastResult, defaultEmotion: defaultEmotion);
    final player = context.read<PlayerProvider>();

    if (SpotifyRemoteService.instance.isSupportedPlatform && hasSpotifyTarget) {
      loadPlaylistIntoPlayer(
        player,
        trackList,
        lastResult,
        defaultEmotion: defaultEmotion,
        fallbackEmotion: playbackEmotion,
        autoplay: false,
      );
      await player.playTrackAtIndex(
        indexOfSelection(trackList, selectedTrack),
        preferInstantPreview: previewUrl.isNotEmpty,
      );
      if (!context.mounted) return;
      await openPlayer(context);
      return;
    }

    // Spotify stopped returning preview clips, so off Android this is the
    // path almost every recommendation takes. The old message only said the
    // song was "not directly playable", which read as a broken button; hand
    // the user the one way they can actually listen.
    if (previewUrl.isEmpty && spotifyUrl.isNotEmpty) {
      if (context.mounted) {
        final isPlaylist =
            (selectedTrack['item_type']?.toString() ?? 'track') == 'playlist';
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(
                isPlaylist
                    ? 'Playlists play through Spotify. Open it there to listen.'
                    : 'No preview for this song here. Open it in Spotify to listen.',
              ),
              action: SnackBarAction(
                label: 'Open Spotify',
                onPressed: () => launchUrl(
                  Uri.parse(spotifyUrl),
                  mode: LaunchMode.externalApplication,
                ),
              ),
            ),
          );
      }
      return;
    }

    loadPlaylistIntoPlayer(
      player,
      trackList,
      lastResult,
      defaultEmotion: defaultEmotion,
      fallbackEmotion: playbackEmotion,
      autoplay: false,
    );
    await player.playTrackAtIndex(
      indexOfSelection(trackList, selectedTrack),
      preferInstantPreview: previewUrl.isNotEmpty,
    );
    if (!context.mounted) return;
    await openPlayer(context);
  }
}
