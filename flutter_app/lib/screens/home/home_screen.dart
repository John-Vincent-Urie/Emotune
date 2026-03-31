import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/player_provider.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../services/api_service.dart';
import '../../services/spotify_remote_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotune_logo.dart';
import '../widgets/track_card.dart';
import '../widgets/mini_player.dart';
import '../widgets/feel_better_dialog.dart';
import 'full_player_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const Duration _progressiveAppendDelay = Duration(milliseconds: 180);

  final _promptCtrl = TextEditingController();
  bool _isAnalyzing = false;
  Map<String, dynamic>? _lastResult;
  String? _aiMessage;
  List<Map<String, dynamic>> _tracks = [];
  bool _loadingMoreTracks = false;
  int _requestSequence = 0;

  @override
  void initState() {
    super.initState();
    final player = context.read<PlayerProvider>();
    player.onFeelBetter = (result) {
      if (mounted) {
        unawaited(_showFeelBetterDialog(result));
      }
    };
  }

  @override
  void dispose() {
    final player = context.read<PlayerProvider>();
    if (player.onFeelBetter != null) {
      player.onFeelBetter = null;
    }
    _promptCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final screenWidth = MediaQuery.sizeOf(context).width;
    final isCompactLayout = screenWidth < 390;
    final composerButtonSize = isCompactLayout ? 44.0 : 48.0;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Header
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  EmoTuneLogo(size: 60, showText: true),
                ],
              ),
            ),

            // Chat/Result area
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_aiMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: isDark
                              ? const Color(0xFF1A1A1A)
                              : Colors.grey.shade100,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isDark
                                ? const Color(0xFF2A2A2A)
                                : Colors.grey.shade300,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _aiMessage!,
                              style: TextStyle(
                                color: isDark ? Colors.white : Colors.black87,
                                fontSize: 14,
                                height: 1.5,
                              ),
                            ),
                            if (_lastResult != null) ...[
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 10, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: AppColors.emotionColors[
                                              _lastResult!['emotion']]
                                          ?.withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(20),
                                      border: Border.all(
                                        color: AppColors.emotionColors[
                                                _lastResult!['emotion']] ??
                                            AppColors.accent,
                                      ),
                                    ),
                                    child: Text(
                                      '${_lastResult!['emotion'].toString().toUpperCase()} '
                                      '${_lastResult!['confidence']}%',
                                      style: TextStyle(
                                        color: AppColors.emotionColors[
                                                _lastResult!['emotion']] ??
                                            AppColors.accent,
                                        fontSize: 11,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                    if (_loadingMoreTracks) ...[
                      Row(
                        children: [
                          const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: AppColors.accent,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Loading the rest of your playlist...',
                              style: TextStyle(
                                color: isDark ? Colors.white54 : Colors.black54,
                                fontSize: 13,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                    ],
                    if (_tracks.isNotEmpty) ...[
                      GridView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          childAspectRatio: 0.85,
                          crossAxisSpacing: 10,
                          mainAxisSpacing: 10,
                        ),
                        itemCount: _tracks.length,
                        itemBuilder: (ctx, i) => TrackCard(
                          track: _tracks[i],
                          onTap: () => _playTrack(i),
                          emotion: _playbackEmotionFromResult(_lastResult),
                        ),
                      ),
                      const SizedBox(height: 80),
                    ],
                    if (_lastResult != null &&
                        _tracks.isEmpty &&
                        !_isAnalyzing) ...[
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: isDark
                              ? const Color(0xFF151515)
                              : Colors.grey.shade50,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isDark
                                ? const Color(0xFF2A2A2A)
                                : Colors.grey.shade300,
                          ),
                        ),
                        child: Text(
                          'No music recommendations were found for that prompt yet. '
                          'Try another feeling, or reconnect Spotify and try again.',
                          style: TextStyle(
                            color: isDark ? Colors.white70 : Colors.black54,
                            fontSize: 13,
                            height: 1.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 80),
                    ],
                    if (_tracks.isEmpty && _aiMessage == null)
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 60),
                          child: Column(
                            children: [
                              Icon(Icons.music_note,
                                  size: 60,
                                  color:
                                      isDark ? Colors.white12 : Colors.black12),
                              const SizedBox(height: 12),
                              Text(
                                'Tell me how you feel...',
                                style: TextStyle(
                                  color:
                                      isDark ? Colors.white30 : Colors.black38,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),

            // Mini player
            const MiniPlayer(),

            // Prompt input
            Container(
              padding: EdgeInsets.fromLTRB(
                isCompactLayout ? 12 : 16,
                8,
                isCompactLayout ? 12 : 16,
                isCompactLayout ? 12 : 16,
              ),
              decoration: BoxDecoration(
                color: isDark ? Colors.black : Colors.white,
                border: Border(
                  top: BorderSide(
                    color:
                        isDark ? const Color(0xFF2A2A2A) : Colors.grey.shade200,
                  ),
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _promptCtrl,
                      style: TextStyle(
                          color: isDark ? Colors.white : Colors.black87),
                      decoration: InputDecoration(
                        hintText: 'I feel......',
                        hintStyle: TextStyle(
                          color: isDark ? Colors.white38 : Colors.black38,
                          fontStyle: FontStyle.italic,
                        ),
                        filled: true,
                        fillColor: isDark
                            ? const Color(0xFF1A1A1A)
                            : Colors.grey.shade100,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(25),
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: isCompactLayout ? 14 : 16,
                          vertical: isCompactLayout ? 10 : 12,
                        ),
                      ),
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _analyze(),
                    ),
                  ),
                  SizedBox(width: isCompactLayout ? 6 : 8),
                  GestureDetector(
                    onTap: _isAnalyzing ? null : _analyze,
                    child: Container(
                      width: composerButtonSize,
                      height: composerButtonSize,
                      decoration: const BoxDecoration(
                        gradient: AppColors.buttonGradient,
                        shape: BoxShape.circle,
                      ),
                      child: _isAnalyzing
                          ? Padding(
                              padding:
                                  EdgeInsets.all(isCompactLayout ? 11 : 12),
                              child: const CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.black),
                            )
                          : Icon(
                              Icons.send,
                              color: Colors.black,
                              size: isCompactLayout ? 18 : 20,
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _analyze() async {
    final text = _promptCtrl.text.trim();
    if (text.isEmpty) return;
    final requestId = ++_requestSequence;
    final studio = context.read<RecommendationStudioProvider>();

    setState(() {
      _isAnalyzing = true;
      _tracks = [];
      _aiMessage = null;
      _loadingMoreTracks = false;
    });

    try {
      final result = await ApiService.analyzeEmotion(
        text,
        outcomeMode: studio.selectedOutcomeMode,
        sessionLengthMinutes: studio.sessionLengthMinutes,
        checkInFrequencyTracks: studio.checkInFrequencyTracks,
        tasteProfile: _currentTasteProfile(),
      );
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      final normalizedTracks = PlayerProvider.normalizeTrackList(
        List<dynamic>.from(result['tracks'] ?? []),
      );
      final continuationToken =
          result['continuation_token']?.toString().trim() ?? '';
      final loadingMoreTracks =
          result['loading_more_tracks'] == true && continuationToken.isNotEmpty;
      setState(() {
        _lastResult = result;
        _aiMessage = result['ai_response'];
        _tracks = normalizedTracks;
        _loadingMoreTracks = loadingMoreTracks;
      });
      _promptCtrl.clear();
      if (normalizedTracks.isNotEmpty) {
        unawaited(_autoplayInitialTrack(normalizedTracks, result));
      }
      if (loadingMoreTracks) {
        unawaited(
          _loadMoreRecommendationTracks(
            requestId: requestId,
            continuationToken: continuationToken,
          ),
        );
      }
    } on ApiException catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _lastResult = null;
        _tracks = [];
        _aiMessage = e.message;
        _loadingMoreTracks = false;
      });
    } catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _lastResult = null;
        _tracks = [];
        _aiMessage =
            'Could not analyze your prompt right now. Please try again.';
        _loadingMoreTracks = false;
      });
    } finally {
      if (mounted && requestId == _requestSequence) {
        setState(() => _isAnalyzing = false);
      }
    }
  }

  Future<void> _autoplayInitialTrack(
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic> result,
  ) async {
    if (!mounted || tracks.isEmpty) {
      return;
    }

    final player = context.read<PlayerProvider>();
    _loadPlaylistIntoPlayer(
      player,
      tracks,
      result,
      autoplay: false,
    );
    try {
      await player.playTrackAtIndex(0, preferInstantPreview: true);
    } catch (_) {
      // Keep the UI responsive even if the first autoplay attempt fails.
    }
  }

  Future<void> _loadMoreRecommendationTracks({
    required int requestId,
    required String continuationToken,
  }) async {
    final hadTracksBefore = _tracks.isNotEmpty;
    try {
      final result = await ApiService.continueRecommendation(continuationToken);
      if (!mounted || requestId != _requestSequence) {
        return;
      }

      final incomingTracks = PlayerProvider.normalizeTrackList(
        List<dynamic>.from(result['tracks'] ?? []),
      );
      final mergedTracks =
          PlayerProvider.mergeTrackLists(_tracks, incomingTracks);
      final newTracks = mergedTracks.skip(_tracks.length).toList();
      final historyId = _historyIdFromResult(result);
      final emotion = _playbackEmotionFromResult(result);
      final player = context.read<PlayerProvider>();
      var startedAutoplayFromContinuation = false;

      if (newTracks.isEmpty) {
        setState(() {
          _lastResult = result;
          _tracks = mergedTracks;
          _loadingMoreTracks = false;
          if ((result['ai_response']?.toString().trim().isNotEmpty ?? false)) {
            _aiMessage = result['ai_response']?.toString();
          }
        });
        return;
      }

      for (final track in newTracks) {
        if (!mounted || requestId != _requestSequence) {
          return;
        }

        final nextVisibleTracks = [..._tracks, track];
        setState(() {
          _lastResult = result;
          _tracks = nextVisibleTracks;
          if ((result['ai_response']?.toString().trim().isNotEmpty ?? false)) {
            _aiMessage = result['ai_response']?.toString();
          }
        });

        final shouldMergeActivePlaylist =
            (historyId != null && player.historyId == historyId) ||
                (historyId == null &&
                    player.currentEmotion == emotion &&
                    player.playlist.isNotEmpty);

        if (!hadTracksBefore && !startedAutoplayFromContinuation) {
          _loadPlaylistIntoPlayer(
            player,
            nextVisibleTracks,
            result,
            autoplay: true,
          );
          startedAutoplayFromContinuation = true;
        } else if (shouldMergeActivePlaylist) {
          _mergePlaylistIntoPlayer(
            player,
            nextVisibleTracks,
            result,
          );
        }

        await Future.delayed(_progressiveAppendDelay);
      }

      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() => _loadingMoreTracks = false);
    } on ApiException {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() => _loadingMoreTracks = false);
    } catch (_) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() => _loadingMoreTracks = false);
    }
  }

  int? _historyIdFromResult(Map<String, dynamic> result) {
    final historyId = result['history_id'];
    if (historyId is int) {
      return historyId;
    }
    if (historyId is num) {
      return historyId.toInt();
    }
    return int.tryParse(historyId?.toString() ?? '');
  }

  Map<String, dynamic> _currentTasteProfile() {
    return context.read<RecommendationStudioProvider>().tasteProfile;
  }

  Map<String, dynamic>? _sessionPlanFromResult(Map<String, dynamic>? result) {
    final raw = result?['session_plan'];
    if (raw is! Map) {
      return null;
    }
    return Map<String, dynamic>.from(raw);
  }

  Map<String, dynamic> _tasteProfileFromResult(Map<String, dynamic>? result) {
    final raw = result?['taste_profile'];
    if (raw is! Map) {
      return _currentTasteProfile();
    }
    return Map<String, dynamic>.from(raw);
  }

  bool _trainOnThisSessionFromResult(Map<String, dynamic>? result) {
    return _tasteProfileFromResult(result)['train_session'] != false;
  }

  String _playbackEmotionFromResult(Map<String, dynamic>? result) {
    final recommendationTarget =
        result?['recommendation_target_emotion']?.toString().trim() ?? '';
    if (recommendationTarget.isNotEmpty) {
      return recommendationTarget;
    }

    final detectedEmotion = result?['emotion']?.toString().trim() ?? '';
    if (detectedEmotion.isNotEmpty) {
      return detectedEmotion;
    }

    return 'mixed';
  }

  void _loadPlaylistIntoPlayer(
    PlayerProvider player,
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic>? result, {
    String? fallbackEmotion,
    bool autoplay = false,
  }) {
    final playbackEmotion = _playbackEmotionFromResult(result);
    player.loadPlaylist(
      tracks,
      playbackEmotion == 'mixed' && fallbackEmotion != null
          ? fallbackEmotion
          : playbackEmotion,
      historyId: _historyIdFromResult(result ?? const <String, dynamic>{}),
      autoplay: autoplay,
      sessionPlan: _sessionPlanFromResult(result),
      tasteProfile: _tasteProfileFromResult(result),
      outcomeMode: result?['outcome_mode']?.toString(),
      outcomeLabel: result?['outcome_label']?.toString(),
      outcomeDescription: result?['outcome_description']?.toString(),
      trainOnThisSession: _trainOnThisSessionFromResult(result),
    );
  }

  void _mergePlaylistIntoPlayer(
    PlayerProvider player,
    List<Map<String, dynamic>> tracks,
    Map<String, dynamic>? result,
  ) {
    player.mergePlaylistTracks(
      tracks,
      emotion: _playbackEmotionFromResult(result),
      historyId: _historyIdFromResult(result ?? const <String, dynamic>{}),
      sessionPlan: _sessionPlanFromResult(result),
      tasteProfile: _tasteProfileFromResult(result),
      outcomeMode: result?['outcome_mode']?.toString(),
      outcomeLabel: result?['outcome_label']?.toString(),
      outcomeDescription: result?['outcome_description']?.toString(),
      trainOnThisSession: _trainOnThisSessionFromResult(result),
    );
  }

  Future<void> _playTrack(int index) async {
    final track = PlayerProvider.normalizeTrack(_tracks[index]);
    _tracks[index] = track;
    final previewUrl = track['preview_url']?.toString().trim() ?? '';
    final spotifyUri = track['uri']?.toString().trim() ?? '';
    final spotifyUrl = track['spotify_url']?.toString().trim() ?? '';
    final trackList = _playlistForSelection(track);
    final hasSpotifyTarget = spotifyUri.isNotEmpty || spotifyUrl.isNotEmpty;
    final playbackEmotion = _playbackEmotionFromResult(_lastResult);

    if (SpotifyRemoteService.instance.isSupportedPlatform && hasSpotifyTarget) {
      _loadPlaylistIntoPlayer(
        context.read<PlayerProvider>(),
        trackList,
        _lastResult,
        fallbackEmotion: playbackEmotion,
        autoplay: false,
      );
      await context.read<PlayerProvider>().playTrackAtIndex(
            trackList.length == 1 ? 0 : index,
            preferInstantPreview: previewUrl.isNotEmpty,
          );
      await _openPlayer();
      return;
    }

    if (previewUrl.isEmpty && spotifyUrl.isNotEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              (track['item_type']?.toString() ?? 'track') == 'playlist'
                  ? 'This playlist needs Android Spotify playback in the current app build.'
                  : 'This recommendation is not directly playable in the current app build.',
            ),
          ),
        );
      }
      return;
    }

    _loadPlaylistIntoPlayer(
      context.read<PlayerProvider>(),
      trackList,
      _lastResult,
      fallbackEmotion: playbackEmotion,
      autoplay: false,
    );
    await context.read<PlayerProvider>().playTrackAtIndex(
          trackList.length == 1 ? 0 : index,
          preferInstantPreview: previewUrl.isNotEmpty,
        );
    await _openPlayer();
  }

  List<Map<String, dynamic>> _playlistForSelection(
    Map<String, dynamic> selectedTrack,
  ) {
    final playlist = PlayerProvider.normalizeTrackList(_tracks);
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

  Future<void> _openPlayer() async {
    if (!mounted) {
      return;
    }
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const FullPlayerScreen(),
    );
  }

  Future<void> _showFeelBetterDialog(Map<String, dynamic> result) async {
    final dialogResult = await showDialog<Map<String, dynamic>?>(
      context: context,
      barrierDismissible: false,
      builder: (_) => FeelBetterDialog(data: result),
    );
    if (!mounted || dialogResult is! Map<String, dynamic>) {
      return;
    }

    final action = dialogResult['action']?.toString().trim() ?? '';
    if (action != 'transition_playlist') {
      return;
    }

    final transitionTracks = PlayerProvider.normalizeTrackList(
      List<dynamic>.from(dialogResult['tracks'] ?? const []),
    );
    if (transitionTracks.isEmpty) {
      return;
    }

    setState(() {
      _lastResult = dialogResult;
      _tracks = transitionTracks;
      _loadingMoreTracks = false;
      if (dialogResult['ai_response']?.toString().trim().isNotEmpty ?? false) {
        _aiMessage = dialogResult['ai_response']?.toString();
      }
    });
  }
}
