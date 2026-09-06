import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
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

  Map<String, dynamic> tasteProfileFromResult(
    Map<String, dynamic>? result,
    Map<String, dynamic> currentTasteProfile,
  ) {
    final raw = result?['taste_profile'];
    if (raw is! Map) {
      return currentTasteProfile;
    }
    return Map<String, dynamic>.from(raw);
  }

  bool trainOnThisSessionFromResult(
    Map<String, dynamic>? result,
    Map<String, dynamic> currentTasteProfile,
  ) {
    return tasteProfileFromResult(result, currentTasteProfile)['train_session'] !=
        false;
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
    Map<String, dynamic> currentTasteProfile, {
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
      tasteProfile: tasteProfileFromResult(result, currentTasteProfile),
      outcomeMode: result?['outcome_mode']?.toString(),
      outcomeLabel: result?['outcome_label']?.toString(),
      outcomeDescription: result?['outcome_description']?.toString(),
      trainOnThisSession:
          trainOnThisSessionFromResult(result, currentTasteProfile),
    );
  }

  void mergePlaylistIntoPlayer(
    PlayerProvider player,
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic>? result,
    Map<String, dynamic> currentTasteProfile, {
    String defaultEmotion = 'mixed',
  }) {
    player.mergePlaylistTracks(
      tracks,
      emotion: playbackEmotionFromResult(result, defaultEmotion: defaultEmotion),
      historyId: historyIdFromResult(result ?? const <String, dynamic>{}),
      sessionPlan: sessionPlanFromResult(result),
      tasteProfile: tasteProfileFromResult(result, currentTasteProfile),
      outcomeMode: result?['outcome_mode']?.toString(),
      outcomeLabel: result?['outcome_label']?.toString(),
      outcomeDescription: result?['outcome_description']?.toString(),
      trainOnThisSession:
          trainOnThisSessionFromResult(result, currentTasteProfile),
    );
  }

  List<Map<String, dynamic>> playlistForSelection(
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic> selectedTrack,
  ) {
    final playlist = PlayerProvider.normalizeTrackList(tracks);
    final selectedTrackId = selectedTrack['id']?.toString().trim() ?? '';
    final selectedTrackUri = selectedTrack['uri']?.toString().trim() ?? '';
    final containsSelection = playlist.any((track) {
      final trackId = track['id']?.toString().trim() ?? '';
      final trackUri = track['uri']?.toString().trim() ?? '';
      return (selectedTrackId.isNotEmpty && trackId == selectedTrackId) ||
          (selectedTrackUri.isNotEmpty && trackUri == selectedTrackUri);
    });
    if (containsSelection && playlist.isNotEmpty) {
      return playlist;
    }
    return [selectedTrack];
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
    required int index,
    required Map<String, dynamic> selectedTrack,
    required Map<String, dynamic>? lastResult,
    required Map<String, dynamic> currentTasteProfile,
    String defaultEmotion = 'mixed',
  }) async {
    final previewUrl = selectedTrack['preview_url']?.toString().trim() ?? '';
    final spotifyUri = selectedTrack['uri']?.toString().trim() ?? '';
    final spotifyUrl = selectedTrack['spotify_url']?.toString().trim() ?? '';
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
        currentTasteProfile,
        defaultEmotion: defaultEmotion,
        fallbackEmotion: playbackEmotion,
        autoplay: false,
      );
      await player.playTrackAtIndex(
        trackList.length == 1 ? 0 : index,
        preferInstantPreview: previewUrl.isNotEmpty,
      );
      if (!context.mounted) return;
      await openPlayer(context);
      return;
    }

    if (previewUrl.isEmpty && spotifyUrl.isNotEmpty) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              (selectedTrack['item_type']?.toString() ?? 'track') == 'playlist'
                  ? 'This playlist needs Android Spotify playback in the current app build.'
                  : 'This recommendation is not directly playable in the current app build.',
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
      currentTasteProfile,
      defaultEmotion: defaultEmotion,
      fallbackEmotion: playbackEmotion,
      autoplay: false,
    );
    await player.playTrackAtIndex(
      trackList.length == 1 ? 0 : index,
      preferInstantPreview: previewUrl.isNotEmpty,
    );
    if (!context.mounted) return;
    await openPlayer(context);
  }
}
