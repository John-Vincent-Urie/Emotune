import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/recommendation_session_controller.dart';
import '../../providers/player_provider.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotune_logo.dart';
import '../widgets/track_card.dart';
import '../widgets/mini_player.dart';
import '../widgets/feel_better_dialog.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const Duration _progressiveAppendDelay = Duration(milliseconds: 180);
  static const _session = RecommendationSessionController();

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
                              ? AppColors.darkCard
                              : Colors.grey.shade100,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isDark
                                ? AppColors.darkBorder
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
                                          ?.withValues(alpha: 0.2),
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
                          emotion: _session.playbackEmotionFromResult(_lastResult),
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
                              ? AppColors.darkCard
                              : Colors.grey.shade50,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isDark
                                ? AppColors.darkBorder
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
                color: isDark ? AppColors.darkBg : Colors.white,
                border: Border(
                  top: BorderSide(
                    color:
                        isDark ? AppColors.darkBorder : Colors.grey.shade200,
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
                            ? AppColors.darkCard
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
        sessionLengthMinutes: studio.sessionLengthMinutes,
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
    _session.loadPlaylistIntoPlayer(
      player,
      tracks,
      result,
      _currentTasteProfile(),
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
      final historyId = _session.historyIdFromResult(result);
      final emotion = _session.playbackEmotionFromResult(result);
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
          _session.loadPlaylistIntoPlayer(
            player,
            nextVisibleTracks,
            result,
            _currentTasteProfile(),
            autoplay: true,
          );
          startedAutoplayFromContinuation = true;
        } else if (shouldMergeActivePlaylist) {
          _session.mergePlaylistIntoPlayer(
            player,
            nextVisibleTracks,
            result,
            _currentTasteProfile(),
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

  Map<String, dynamic> _currentTasteProfile() {
    return context.read<RecommendationStudioProvider>().tasteProfile;
  }

  Future<void> _playTrack(int index) async {
    final track = PlayerProvider.normalizeTrack(_tracks[index]);
    _tracks[index] = track;
    await _session.playTrackFromList(
      context,
      tracks: _tracks,
      index: index,
      selectedTrack: track,
      lastResult: _lastResult,
      currentTasteProfile: _currentTasteProfile(),
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
