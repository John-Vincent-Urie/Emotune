import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/recommendation_session_controller.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../providers/player_provider.dart';
import '../../widgets/emotion_chip.dart';
import '../../widgets/emotune_page_header.dart';
import '../widgets/song_count_line.dart';
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

  String? _selectedEmotion;
  Map<String, dynamic>? _lastResult;
  List<dynamic> _tracks = [];
  bool _loading = false;
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
      body: SafeArea(
        child: Column(
        children: [
          EmoTunePageHeader(
            title: 'Recommendations',
            titleIcon: Icon(
              Icons.explore_rounded,
              color: context.emoColors.accentText,
              size: 18,
            ),
          ),
          // Emotion selector
          SizedBox(
            height: 44,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 20),
              itemCount: _emotions.length,
              separatorBuilder: (_, __) => const SizedBox(width: 9),
              itemBuilder: (ctx, i) {
                final em = _emotions[i];
                return EmotionChip(
                  label: '${em[0].toUpperCase()}${em.substring(1)}',
                  color: AppColors.emotionColors[em] ?? AppColors.accent,
                  selected: _selectedEmotion == em,
                  onTap: () => _selectEmotion(em),
                );
              },
            ),
          ),
          const SizedBox(height: 8),

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
                                      color: context.emoColors.textSecondary),
                                ),
                              ],
                            ),
                          )
                        : Column(
                            children: [
                              Padding(
                                padding:
                                    const EdgeInsets.fromLTRB(16, 12, 16, 0),
                                child: SongCountLine(
                                  result: _lastResult,
                                  shown: _tracks.length,
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
    });

    try {
      final result = await ApiService.recommendByEmotion(
        emotion,
        text: 'Play songs that fit a $emotion mood.',
        sessionLengthMinutes: studio.sessionLengthMinutes,
      );
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      final normalizedTracks = PlayerProvider.normalizeTrackList(
        List<dynamic>.from(result['tracks'] ?? []),
      );
      setState(() {
        _lastResult = result;
        _tracks = normalizedTracks;
        _loading = false;
        _errorMessage = null;
      });
    } on ApiException catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _loading = false;
        _lastResult = null;
        _errorMessage = e.message;
      });
    } catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _loading = false;
        _lastResult = null;
        _errorMessage = 'Could not load recommendations right now.';
      });
    }
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
      selectedTrack: selectedTrack,
      lastResult: _lastResult,
      defaultEmotion: _selectedEmotion ?? 'mixed',
    );
  }
}
