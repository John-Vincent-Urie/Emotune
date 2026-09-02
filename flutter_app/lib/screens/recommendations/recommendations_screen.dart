import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/recommendation_session_controller.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../providers/player_provider.dart';
import '../widgets/track_card.dart';

class RecommendationsScreen extends StatefulWidget {
  const RecommendationsScreen({
    super.key,
    this.isActive = false,
  });

  final bool isActive;

  @override
  State<RecommendationsScreen> createState() => _RecommendationsScreenState();
}

class _RecommendationsScreenState extends State<RecommendationsScreen> {
  static const String _defaultEmotion = 'happy';
  static const Duration _progressiveAppendDelay = Duration(milliseconds: 180);
  static const _session = RecommendationSessionController();

  final List<String> _emotions = [
    'happy',
    'sad',
    'angry',
    'motivational',
    'fear',
    'depressing',
    'surprising',
    'stressed',
    'calm',
    'lonely',
    'romantic',
    'nostalgic',
    'mixed',
  ];

  final List<String> _emotionEmojis = [
    '😊',
    '😢',
    '😠',
    '💪',
    '😨',
    '😔',
    '😲',
    '😤',
    '😌',
    '🥺',
    '💕',
    '🌅',
    '🎭',
  ];

  String? _selectedEmotion;
  Map<String, dynamic>? _lastResult;
  List<dynamic> _tracks = [];
  bool _loading = false;
  bool _loadingMoreTracks = false;
  String? _errorMessage;
  int _requestSequence = 0;

  @override
  void initState() {
    super.initState();
    _scheduleDefaultEmotionSelectionIfNeeded();
  }

  @override
  void didUpdateWidget(covariant RecommendationsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      _scheduleDefaultEmotionSelectionIfNeeded();
    }
  }

  void _scheduleDefaultEmotionSelectionIfNeeded() {
    if (!widget.isActive || _selectedEmotion == _defaultEmotion) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !widget.isActive || _selectedEmotion == _defaultEmotion) {
        return;
      }
      unawaited(_selectEmotion(_defaultEmotion));
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Recommendations 🎵'),
      ),
      body: Column(
        children: [
          // Emotion selector
          Container(
            height: 80,
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: _emotions.length,
              itemBuilder: (ctx, i) {
                final em = _emotions[i];
                final emoji = _emotionEmojis[i];
                final isSelected = _selectedEmotion == em;
                final color = AppColors.emotionColors[em] ?? AppColors.accent;

                return GestureDetector(
                  onTap: () => _selectEmotion(em),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.only(right: 10),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: isSelected ? color : color.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                          color: isSelected ? color : color.withValues(alpha: 0.3)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(emoji, style: const TextStyle(fontSize: 16)),
                        const SizedBox(width: 6),
                        Text(
                          '${em[0].toUpperCase()}${em.substring(1)}',
                          style: TextStyle(
                            color: isSelected
                                ? Colors.white
                                : (isDark ? Colors.white54 : Colors.black54),
                            fontWeight: isSelected
                                ? FontWeight.bold
                                : FontWeight.normal,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),

          // Tracks
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _errorMessage != null
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          child: Text(
                            _errorMessage!,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: isDark ? Colors.white54 : Colors.black54,
                            ),
                          ),
                        ),
                      )
                    : _tracks.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                if (_loadingMoreTracks) ...[
                                  const SizedBox(
                                    width: 28,
                                    height: 28,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2.5,
                                      color: AppColors.accent,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  Text(
                                    'Finding songs for this mood...',
                                    style: TextStyle(
                                      color: isDark
                                          ? Colors.white54
                                          : Colors.black54,
                                    ),
                                  ),
                                ] else ...[
                                  Icon(Icons.music_note,
                                      size: 60,
                                      color: isDark
                                          ? Colors.white12
                                          : Colors.black12),
                                  const SizedBox(height: 12),
                                  Text(
                                    _selectedEmotion == null
                                        ? 'Select a mood above'
                                        : 'No recommendations found for this mood yet',
                                    style: TextStyle(
                                        color: isDark
                                            ? Colors.white38
                                            : Colors.black38),
                                  ),
                                ],
                              ],
                            ),
                          )
                        : Column(
                            children: [
                              if (_loadingMoreTracks)
                                Padding(
                                  padding:
                                      const EdgeInsets.fromLTRB(16, 12, 16, 0),
                                  child: Row(
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
                                          'Loading more songs for this mood...',
                                          style: TextStyle(
                                            color: isDark
                                                ? Colors.white54
                                                : Colors.black54,
                                            fontSize: 13,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              Expanded(
                                child: GridView.builder(
                                  padding: const EdgeInsets.all(16),
                                  gridDelegate:
                                      const SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: 2,
                                    childAspectRatio: 0.85,
                                    crossAxisSpacing: 10,
                                    mainAxisSpacing: 10,
                                  ),
                                  itemCount: _tracks.length,
                                  itemBuilder: (ctx, i) => TrackCard(
                                    track:
                                        Map<String, dynamic>.from(_tracks[i]),
                                    onTap: () => _playFrom(i),
                                    emotion: _session.playbackEmotionFromResult(
                                      _lastResult,
                                      defaultEmotion: _selectedEmotion ?? 'mixed',
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
          ),
        ],
      ),
    );
  }

  Future<void> _selectEmotion(String emotion) async {
    final requestId = ++_requestSequence;
    final studio = context.read<RecommendationStudioProvider>();
    setState(() {
      _selectedEmotion = emotion;
      _lastResult = null;
      _loading = true;
      _tracks = [];
      _errorMessage = null;
      _loadingMoreTracks = false;
    });

    try {
      final result = await ApiService.recommendByEmotion(
        emotion,
        text: 'Play songs that fit a $emotion mood.',
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
        _tracks = normalizedTracks;
        _loading = false;
        _errorMessage = null;
        _loadingMoreTracks = loadingMoreTracks;
      });
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
        _loading = false;
        _lastResult = null;
        _errorMessage = e.message;
        _loadingMoreTracks = false;
      });
    } catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _loading = false;
        _lastResult = null;
        _errorMessage = 'Could not load recommendations right now.';
        _loadingMoreTracks = false;
      });
    }
  }

  Future<void> _loadMoreRecommendationTracks({
    required int requestId,
    required String continuationToken,
  }) async {
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
      final emotion = _session.playbackEmotionFromResult(
        result,
        defaultEmotion: _selectedEmotion ?? 'mixed',
      );
      final historyId = _session.historyIdFromResult(result);
      final player = context.read<PlayerProvider>();

      if (newTracks.isEmpty) {
        final shouldMergeActivePlaylist =
            (historyId != null && player.historyId == historyId) ||
                (historyId == null &&
                    player.currentEmotion == emotion &&
                    player.playlist.isNotEmpty);
        setState(() {
          _lastResult = result;
          _tracks = mergedTracks;
          _loadingMoreTracks = false;
        });
        if (shouldMergeActivePlaylist) {
          _session.mergePlaylistIntoPlayer(
            player,
            mergedTracks.cast<Map<String, dynamic>>(),
            result,
            _currentTasteProfile(),
            defaultEmotion: _selectedEmotion ?? 'mixed',
          );
        }
        return;
      }

      for (final track in newTracks) {
        if (!mounted || requestId != _requestSequence) {
          return;
        }

        final nextVisibleTracks = PlayerProvider.normalizeTrackList([
          ..._tracks,
          track,
        ]);
        setState(() {
          _lastResult = result;
          _tracks = nextVisibleTracks;
        });

        final shouldMergeActivePlaylist =
            (historyId != null && player.historyId == historyId) ||
                (historyId == null &&
                    player.currentEmotion == emotion &&
                    player.playlist.isNotEmpty);
        if (shouldMergeActivePlaylist) {
          _session.mergePlaylistIntoPlayer(
            player,
            nextVisibleTracks,
            result,
            _currentTasteProfile(),
            defaultEmotion: _selectedEmotion ?? 'mixed',
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

  Future<void> _playFrom(int index) async {
    final selectedTrack = PlayerProvider.normalizeTrack(
      Map<String, dynamic>.from(_tracks[index]),
    );
    _tracks[index] = selectedTrack;
    final normalizedTracks =
        _tracks.map((track) => Map<String, dynamic>.from(track)).toList();
    await _session.playTrackFromList(
      context,
      tracks: normalizedTracks,
      index: index,
      selectedTrack: selectedTrack,
      lastResult: _lastResult,
      currentTasteProfile: _currentTasteProfile(),
      defaultEmotion: _selectedEmotion ?? 'mixed',
    );
  }
}
