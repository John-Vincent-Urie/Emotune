import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/recommendation_session_controller.dart';
import '../../providers/player_provider.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import 'widgets/home_empty_state.dart';
import 'widgets/home_header.dart';
import 'widgets/mood_composer.dart';
import '../widgets/track_card.dart';
import '../widgets/mini_player.dart';
import '../widgets/feel_better_dialog.dart';
import '../support/support_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  static const Duration _progressiveAppendDelay = Duration(milliseconds: 180);
  static const _session = RecommendationSessionController();

  final _promptCtrl = TextEditingController();
  bool _isAnalyzing = false;
  Map<String, dynamic>? _lastResult;
  String? _aiMessage;
  bool _isCrisis = false;
  // Gentle check-in from the backend's concern tier; music still plays.
  Map<String, dynamic>? _supportCheckIn;
  List<Map<String, dynamic>> _tracks = [];
  bool _loadingMoreTracks = false;
  int _requestSequence = 0;
  bool? _reduceMotion;
  bool _entranceStarted = false;
  late final AnimationController _entrance;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
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
    _entrance.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce == _reduceMotion) return;
    _reduceMotion = reduce;
    if (reduce) {
      _entrance.value = 1;
      _entranceStarted = true;
    } else if (!_entranceStarted) {
      _entranceStarted = true;
      _entrance.forward();
    }
  }

  bool get _isEmptyState => _tracks.isEmpty && _aiMessage == null;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final reduceMotion = _reduceMotion ?? false;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Brand header -- fixed above the body, so it stays put once the
            // results replace the empty state.
            HomeHeader(entrance: _entrance, reduceMotion: reduceMotion),

            // Chat/Result area
            Expanded(
              child: _isEmptyState
                  ? LayoutBuilder(
                      builder: (context, constraints) => SingleChildScrollView(
                        child: ConstrainedBox(
                          // Centre in whatever space is left, but stay
                          // scrollable so the chips survive a short screen
                          // with the keyboard up.
                          constraints:
                              BoxConstraints(minHeight: constraints.maxHeight),
                          child: Center(
                            child: HomeEmptyState(
                              entrance: _entrance,
                              reduceMotion: reduceMotion,
                            ),
                          ),
                        ),
                      ),
                    )
                  : SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_aiMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: _isCrisis
                              ? const Color(0xFFFFB020).withValues(alpha: 0.12)
                              : colors.card,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: _isCrisis
                                ? const Color(0xFFFFB020)
                                : colors.divider,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (_isCrisis) ...[
                              const Row(
                                children: [
                                  Icon(
                                    Icons.favorite,
                                    color: Color(0xFFFFB020),
                                    size: 18,
                                  ),
                                  SizedBox(width: 8),
                                  Text(
                                    "We'd rather check in than play a song",
                                    style: TextStyle(
                                      color: Color(0xFFFFB020),
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                            ],
                            Text(
                              _aiMessage!,
                              style: TextStyle(
                                color: colors.textPrimary,
                                fontSize: 14,
                                height: 1.5,
                              ),
                            ),
                            if (_isCrisis) ...[
                              const SizedBox(height: 12),
                              FilledButton.icon(
                                style: FilledButton.styleFrom(
                                  backgroundColor: const Color(0xFFFFB020),
                                  foregroundColor: Colors.black,
                                ),
                                icon: const Icon(Icons.support_agent),
                                label: const Text('Get support now'),
                                onPressed: _openCrisisSupport,
                              ),
                            ],
                            if (!_isCrisis && _lastResult != null) ...[
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
                    if (_supportCheckIn != null && !_isCrisis) ...[
                      _buildCheckInBanner(colors),
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
                                color: colors.textSecondary,
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
                        !_isAnalyzing &&
                        !_isCrisis) ...[
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: colors.card,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: colors.divider),
                        ),
                        child: Text(
                          'No music recommendations were found for that prompt yet. '
                          'Try another feeling, or reconnect Spotify and try again.',
                          style: TextStyle(
                            color: colors.textSecondary,
                            fontSize: 13,
                            height: 1.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 80),
                    ],
                  ],
                ),
              ),
            ),

            // Mini player
            const MiniPlayer(),

            // Prompt input -- present from the first frame, not part of the
            // entrance sequence.
            MoodComposer(
              controller: _promptCtrl,
              isBusy: _isAnalyzing,
              onSubmit: _analyze,
              reduceMotion: reduceMotion,
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
      _isCrisis = false;
      _supportCheckIn = null;
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
      final isCrisis = result['crisis'] == true;
      final checkIn = result['support_check_in'];
      setState(() {
        _lastResult = result;
        _aiMessage = result['ai_response'];
        _isCrisis = isCrisis;
        _supportCheckIn =
            checkIn is Map ? Map<String, dynamic>.from(checkIn) : null;
        _tracks = normalizedTracks;
        _loadingMoreTracks = loadingMoreTracks;
      });
      _promptCtrl.clear();
      if (isCrisis) {
        // A song from the previous request must not keep playing under the
        // support screen. Paused rather than cleared, so nothing is lost.
        final player = context.read<PlayerProvider>();
        if (player.isPlaying) {
          unawaited(player.togglePlayPause());
        }
        // Full-screen so it cannot be scrolled past; the card stays behind it
        // with a button to reopen it.
        unawaited(_openCrisisSupport());
      }
      if (!isCrisis && normalizedTracks.isNotEmpty) {
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

  Future<void> _openCrisisSupport() {
    return SupportScreen.open(
      context,
      level: 'crisis',
      message: _aiMessage ?? '',
      resources: List<dynamic>.from(_lastResult?['support_resources'] ?? []),
    );
  }

  Widget _buildCheckInBanner(EmoTuneColors colors) {
    const amber = Color(0xFFFFB020);
    final checkIn = _supportCheckIn!;
    final message = checkIn['message']?.toString() ?? '';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: amber.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: amber.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.favorite, color: amber, size: 18),
              SizedBox(width: 8),
              Text(
                'Checking in on you',
                style: TextStyle(
                  color: amber,
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            message,
            style: TextStyle(color: colors.textPrimary, fontSize: 14, height: 1.5),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              TextButton(
                onPressed: () => SupportScreen.open(
                  context,
                  level: 'concern',
                  message: message,
                  resources: List<dynamic>.from(checkIn['resources'] ?? []),
                ),
                child: const Text(
                  'Talk to a counselor',
                  style: TextStyle(color: amber, fontWeight: FontWeight.bold),
                ),
              ),
              const Spacer(),
              TextButton(
                onPressed: () => setState(() => _supportCheckIn = null),
                child: Text(
                  "I'm okay",
                  style: TextStyle(color: colors.textSecondary),
                ),
              ),
            ],
          ),
        ],
      ),
    );
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
