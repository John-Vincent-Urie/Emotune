import 'dart:async';
import 'dart:math' as math;

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
import '../widgets/song_count_line.dart';
import '../widgets/track_card.dart';
import '../widgets/mini_player.dart';
import '../widgets/feel_better_dialog.dart';
import '../support/support_contact_quick_list.dart';
import '../support/support_screen.dart';
import '../../services/support_contacts.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  static const _session = RecommendationSessionController();

  final _promptCtrl = TextEditingController();
  bool _isAnalyzing = false;
  Map<String, dynamic>? _lastResult;
  String? _aiMessage;
  // A failed analyze. Kept apart from [_aiMessage] so an error never renders
  // as if it were EmoTune's reply.
  String? _analyzeError;
  bool _analyzeErrorIsNetwork = false;
  bool _isCrisis = false;
  // Gentle check-in from the backend's concern tier; music still plays.
  Map<String, dynamic>? _supportCheckIn;
  List<Map<String, dynamic>> _tracks = [];
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

  bool get _isEmptyState =>
      _tracks.isEmpty && _aiMessage == null && _analyzeError == null;

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
            // Dropped on short (landscape) screens: header, mini player and
            // composer together left the results area with zero height.
            if (MediaQuery.sizeOf(context).height >= 520)
              HomeHeader(entrance: _entrance, reduceMotion: reduceMotion),

            // Chat/Result area
            Expanded(
              child: _isEmptyState
                  ? LayoutBuilder(
                      builder: (context, constraints) => SingleChildScrollView(
                        // Room for the orb's glow: in landscape the content
                        // outgrows the space and the scroll view's clip edge
                        // cut the orb off.
                        padding: const EdgeInsets.symmetric(vertical: 32),
                        child: ConstrainedBox(
                          // Centre in whatever space is left, but stay
                          // scrollable so the chips survive a short screen
                          // with the keyboard up.
                          constraints: BoxConstraints(
                            minHeight: math.max(0, constraints.maxHeight - 64),
                          ),
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
                    if (_analyzeError != null) ...[
                      _buildAnalyzeError(colors),
                      const SizedBox(height: 16),
                    ],
                    // First, above the reply and the playlist: on a 360x820
                    // phone the last contact used to sit under the mini
                    // player until the user thought to scroll.
                    if (_supportCheckIn != null && !_isCrisis) ...[
                      _buildCheckInBanner(colors),
                      const SizedBox(height: 16),
                    ],
                    if (_aiMessage != null) ...[
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: _isCrisis
                              ? const Color(0xFFFFB020).withValues(alpha: 0.12)
                              : colors.card,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: _isCrisis ? colors.safety : colors.divider,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (_isCrisis) ...[
                              Row(
                                children: [
                                  Icon(
                                    Icons.favorite,
                                    color: colors.safety,
                                    size: 18,
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      "We'd rather check in than play a song",
                                      style: TextStyle(
                                        color: colors.safety,
                                        fontSize: 13,
                                        fontWeight: FontWeight.bold,
                                      ),
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
                                  backgroundColor: colors.safety,
                                  foregroundColor: colors.onSafety,
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
                                    // The mood color stays on the tint and
                                    // border; as text it fell to 1.3:1
                                    // (happy, light) and 1.9:1 (fear, dark).
                                    child: Text(
                                      '${_lastResult!['emotion'].toString().toUpperCase()} '
                                      '${_lastResult!['confidence']}%',
                                      style: TextStyle(
                                        color: colors.textPrimary,
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
                    if (_tracks.isNotEmpty) ...[
                      SongCountLine(result: _lastResult, shown: _tracks.length),
                      const SizedBox(height: 10),
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
    if (text.isEmpty) {
      // Sending nothing used to do nothing at all, which read as broken.
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(
            content: Text('Type a few words about how you feel first.'),
          ),
        );
      return;
    }
    // Drop the keyboard so the reply and playlist aren't hidden under it.
    FocusManager.instance.primaryFocus?.unfocus();
    final requestId = ++_requestSequence;
    final studio = context.read<RecommendationStudioProvider>();

    setState(() {
      _isAnalyzing = true;
      _tracks = [];
      _aiMessage = null;
      _analyzeError = null;
      _analyzeErrorIsNetwork = false;
      _isCrisis = false;
      _supportCheckIn = null;
    });

    try {
      final result = await ApiService.analyzeEmotion(
        text,
        sessionLengthMinutes: studio.sessionLengthMinutes,
      );
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      final normalizedTracks = PlayerProvider.normalizeTrackList(
        List<dynamic>.from(result['tracks'] ?? []),
      );
      final isCrisis = result['crisis'] == true;
      final checkIn = result['support_check_in'];
      setState(() {
        _lastResult = result;
        _aiMessage = result['ai_response'];
        _isCrisis = isCrisis;
        _supportCheckIn =
            checkIn is Map ? Map<String, dynamic>.from(checkIn) : null;
        _tracks = normalizedTracks;
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
    } on ApiException catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _lastResult = null;
        _tracks = [];
        _analyzeError = e.message;
        // No status means the server was never reached.
        _analyzeErrorIsNetwork = e.statusCode == null;
        });
    } catch (e) {
      if (!mounted || requestId != _requestSequence) {
        return;
      }
      setState(() {
        _lastResult = null;
        _tracks = [];
        _analyzeError =
            'Could not analyze your prompt right now. Please try again.';
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
      about: _lastResult?['support_about']?.toString() ?? 'self',
    );
  }

  /// A failed analyze, styled as a notice rather than EmoTune's reply. Crisis
  /// detection runs on the server, so whatever the user wrote got no safety
  /// check; the card always offers the support contacts bundled in the app.
  Widget _buildAnalyzeError(EmoTuneColors colors) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.cloud_off_rounded, color: colors.textSecondary, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Semantics(
                  liveRegion: true,
                  child: Text(
                    _analyzeError!,
                    style: TextStyle(
                      color: colors.textPrimary,
                      fontSize: 14,
                      height: 1.45,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextButton.icon(
            style: TextButton.styleFrom(
              foregroundColor: colors.safety,
              padding: EdgeInsets.zero,
            ),
            icon: const Icon(Icons.support_agent, size: 18),
            label: const Text(
              'Need to talk to someone now?',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            onPressed: () => SupportScreen.open(
              context,
              level: 'concern',
              message: _analyzeErrorIsNetwork
                  ? "EmoTune can't connect right now, but these people can "
                      'be reached by phone.'
                  : 'EmoTune hit a problem, but these people can be reached '
                      'by phone.',
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCheckInBanner(EmoTuneColors colors) {
    const amberTint = Color(0xFFFFB020);
    final checkIn = _supportCheckIn!;
    final message = checkIn['message']?.toString() ?? '';
    final about = checkIn['about']?.toString() ?? 'self';
    final resources = supportContactsOrBundled(
      List<dynamic>.from(checkIn['resources'] ?? const []),
    );
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: amberTint.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.safety.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.favorite, color: colors.safety, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  about == 'someone_else'
                      ? 'Help for someone you care about'
                      : 'Checking in on you',
                  style: TextStyle(
                    color: colors.safety,
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                  ),
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
          SupportContactQuickList(resources: resources),
          const SizedBox(height: 4),
          Row(
            children: [
              TextButton(
                onPressed: () => SupportScreen.open(
                  context,
                  level: 'concern',
                  message: message,
                  resources: resources,
                  about: about,
                ),
                child: Text(
                  'More ways to get support',
                  style: TextStyle(
                    color: colors.safety,
                    fontWeight: FontWeight.bold,
                  ),
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
      autoplay: false,
    );
    try {
      await player.playTrackAtIndex(0, preferInstantPreview: true);
    } catch (_) {
      // Keep the UI responsive even if the first autoplay attempt fails.
    }
  }

  Future<void> _playTrack(int index) async {
    final track = PlayerProvider.normalizeTrack(_tracks[index]);
    _tracks[index] = track;
    await _session.playTrackFromList(
      context,
      tracks: _tracks,
      selectedTrack: track,
      lastResult: _lastResult,
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
      if (dialogResult['ai_response']?.toString().trim().isNotEmpty ?? false) {
        _aiMessage = dialogResult['ai_response']?.toString();
      }
    });
  }
}
