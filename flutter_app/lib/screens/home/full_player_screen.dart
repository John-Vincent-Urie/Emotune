import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/player_provider.dart';
import '../../theme/app_theme.dart';

class FullPlayerScreen extends StatelessWidget {
  const FullPlayerScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final player = context.watch<PlayerProvider>();
    final track = player.currentTrack;

    if (track == null) {
      return const SizedBox.shrink();
    }

    final emotion = player.currentEmotion ?? 'mixed';
    final emotionColor = AppColors.emotionColors[emotion] ?? AppColors.accent;
    final queue = player.activeQueue;
    final queueTitle = _queueTitle(player, queue);
    final queueSubtitle = _queueSubtitle(player);
    final queueMeta = _queueMeta(player, queue);
    final isWaitingForSpotifyQueue =
        player.isResolvingContextQueue && player.contextQueue.isEmpty;
    final durationMs = player.duration.inMilliseconds;
    final displayPositionMs = player.displayPosition.inMilliseconds;
    final sliderEnabled = durationMs > 0;
    final progress = sliderEnabled
        ? (displayPositionMs / durationMs).clamp(0.0, 1.0)
        : 0.0;

    return Container(
      height: MediaQuery.of(context).size.height * 0.94,
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            _blendWithBlack(emotionColor, 0.20),
            _blendWithBlack(emotionColor, 0.55),
            const Color(0xFF161616),
            const Color(0xFF111111),
          ],
          stops: const [0.0, 0.24, 0.55, 1.0],
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          children: [
            const SizedBox(height: 10),
            Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.35),
                borderRadius: BorderRadius.circular(999),
              ),
            ),
            Expanded(
              child: CustomScrollView(
                physics: const BouncingScrollPhysics(),
                slivers: [
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(18, 18, 18, 0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _HeaderArtwork(
                                imageUrl: track['image']?.toString() ?? '',
                                accentColor: emotionColor,
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        _queueLabel(player, track),
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.85),
                                          fontSize: 13,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                      const SizedBox(height: 6),
                                      Text(
                                        queueTitle,
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 28,
                                          height: 0.95,
                                          fontWeight: FontWeight.w800,
                                        ),
                                        maxLines: 3,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        queueSubtitle,
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.75),
                                          fontSize: 13,
                                          height: 1.3,
                                        ),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      const SizedBox(height: 10),
                                      Row(
                                        children: [
                                          CircleAvatar(
                                            radius: 11,
                                            backgroundColor: Colors.black.withOpacity(0.28),
                                            child: const Icon(
                                              Icons.graphic_eq_rounded,
                                              size: 13,
                                              color: Colors.white,
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Expanded(
                                            child: Text(
                                              queueMeta,
                                              style: TextStyle(
                                                color: Colors.white.withOpacity(0.88),
                                                fontSize: 13,
                                                fontWeight: FontWeight.w600,
                                              ),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 18),
                          _buildStatusPill(player),
                          if (player.hasRecommendationContext) ...[
                            const SizedBox(height: 14),
                            _SessionPlanCard(player: player),
                          ],
                          const SizedBox(height: 18),
                          _ControlStrip(
                            player: player,
                            track: track,
                            onFavorite: () => _toggleFavorite(context, player, track),
                          ),
                          const SizedBox(height: 14),
                          SliderTheme(
                            data: SliderTheme.of(context).copyWith(
                              trackHeight: 3,
                              thumbShape: const RoundSliderThumbShape(
                                enabledThumbRadius: 5,
                              ),
                              overlayShape: SliderComponentShape.noOverlay,
                              activeTrackColor: Colors.white,
                              inactiveTrackColor: Colors.white24,
                              thumbColor: Colors.white,
                            ),
                            child: Slider(
                              value: progress.clamp(0.0, 1.0),
                              onChangeStart:
                                  sliderEnabled
                                      ? (_) => player.beginSeekPreview()
                                      : null,
                              onChanged:
                                  sliderEnabled
                                      ? (value) {
                                        final duration = Duration(
                                          milliseconds: (value * durationMs).round(),
                                        );
                                        player.updateSeekPreview(duration);
                                      }
                                      : null,
                              onChangeEnd:
                                  sliderEnabled
                                      ? (value) {
                                        final duration = Duration(
                                          milliseconds: (value * durationMs).round(),
                                        );
                                        player.commitSeekPreview(duration);
                                      }
                                      : null,
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                _MetaText(_formatDuration(player.displayPosition)),
                                _MetaText(_formatDuration(player.duration)),
                              ],
                            ),
                          ),
                          const SizedBox(height: 22),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            child: Row(
                              children: [
                                Text(
                                  '#',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.5),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(width: 16),
                                Expanded(
                                  child: Text(
                                    'Title',
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.5),
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                                Icon(
                                  Icons.access_time_rounded,
                                  size: 18,
                                  color: Colors.white.withOpacity(0.5),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 10),
                          Divider(
                            height: 1,
                            color: Colors.white.withOpacity(0.10),
                          ),
                          const SizedBox(height: 8),
                        ],
                      ),
                    ),
                  ),
                  if (isWaitingForSpotifyQueue)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(14, 0, 14, 20),
                        child: _ContextLoadingCard(track: track),
                      ),
                    )
                  else
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
                      sliver: SliverList(
                        delegate: SliverChildBuilderDelegate(
                          (context, index) {
                            final item = queue[index];
                            return _QueueRow(
                              track: item,
                              index: index,
                              isCurrent: _isCurrentQueueItem(player, item, index),
                              isPlaying: player.isPlaying,
                              emotionColor: emotionColor,
                              onTap: player.isShowingCurrentRemoteTrackOnly
                                  ? null
                                  : () => player.playQueueItem(item, index),
                            );
                          },
                          childCount: queue.length,
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

  Widget _buildStatusPill(PlayerProvider player) {
    if (_shouldHidePlaybackStatus(player)) {
      return const SizedBox.shrink();
    }

    final isWaitingForSpotifyQueue =
        player.isResolvingContextQueue && player.contextQueue.isEmpty;
    final label = isWaitingForSpotifyQueue
        ? 'Loading Spotify queue in background'
        : player.playbackStatusLabel;
    final detail = isWaitingForSpotifyQueue
        ? 'Spotify is resolving the selected queue while EmoTune stays in front.'
        : player.playbackStatusDetail;
    final icon = isWaitingForSpotifyQueue
        ? Icons.sync_rounded
        : player.isUsingSpotifyRemote
            ? Icons.devices_rounded
            : Icons.headphones_rounded;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withOpacity(0.10)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            icon,
            size: 18,
            color: Colors.white.withOpacity(0.88),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.92),
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (detail != null && detail.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    detail,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.72),
                      fontSize: 11,
                      height: 1.3,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  bool _shouldHidePlaybackStatus(PlayerProvider player) {
    if (player.errorMessage != null) {
      return true;
    }
    return switch (player.playbackStatusCode) {
      'spotify_background_unavailable' => true,
      'not_directly_playable' => true,
      'preview_error' => true,
      _ => false,
    };
  }

  String _queueLabel(PlayerProvider player, Map<String, dynamic> track) {
    final itemType = player.currentContext?['type']?.toString() ??
        track['item_type']?.toString() ??
        'track';
    if (itemType == 'playlist') {
      return 'Public Playlist';
    }
    if (itemType == 'album') {
      return 'Album';
    }
    if (itemType == 'artist') {
      return 'Artist Radio';
    }
    return 'Mood Queue';
  }

  String _queueTitle(PlayerProvider player, List<Map<String, dynamic>> queue) {
    final currentContext = player.currentContext;
    final contextTitle = currentContext?['title']?.toString().trim() ?? '';
    if (contextTitle.isNotEmpty) {
      return contextTitle;
    }

    final track = player.currentTrack ?? const <String, dynamic>{};
    final itemType = track['item_type']?.toString() ?? 'track';
    if (itemType == 'playlist' || itemType == 'artist') {
      return track['name']?.toString() ?? 'EmoTune Mix';
    }

    final emotion = player.currentEmotion ?? 'mixed';
    final label = '${emotion[0].toUpperCase()}${emotion.substring(1)}';
    if (queue.length > 1) {
      return '$label Mix';
    }
    return track['name']?.toString() ?? '$label Mix';
  }

  String _queueSubtitle(PlayerProvider player) {
    final currentContext = player.currentContext;
    final contextSubtitle = currentContext?['subtitle']?.toString().trim() ?? '';
    final contextType = currentContext?['type']?.toString().trim() ?? '';

    if (contextSubtitle.isNotEmpty) {
      if (contextType == 'playlist') {
        return contextSubtitle;
      }
      if (contextType == 'album') {
        return contextSubtitle;
      }
      if (contextType == 'artist') {
        return contextSubtitle;
      }
      return contextSubtitle;
    }

    final track = player.currentTrack ?? const <String, dynamic>{};
    final artist = track['artist']?.toString().trim() ?? '';
    final album = track['album']?.toString().trim() ?? '';
    final itemType = track['item_type']?.toString() ?? 'track';

    if (itemType == 'playlist') {
      return 'Auto-curated inside EmoTune for your current mood.';
    }
    if (itemType == 'artist') {
      return artist.isNotEmpty ? '$artist radio inside EmoTune.' : 'Artist radio inside EmoTune.';
    }

    if (artist.isNotEmpty && album.isNotEmpty) {
      return '$artist // $album';
    }
    if (artist.isNotEmpty) {
      return artist;
    }
    return 'Curated inside EmoTune for your current mood.';
  }

  String _queueMeta(PlayerProvider player, List<Map<String, dynamic>> queue) {
    final count = queue.length;
    final totalDurationMs = queue.fold<int>(
      0,
      (sum, item) => sum + ((item['duration_ms'] as num?)?.toInt() ?? 0),
    );
    final currentContextType = player.currentContext?['type']?.toString() ?? '';
    final itemLabel = count == 1 ? 'track' : 'tracks';
    final lengthLabel = totalDurationMs > 0
        ? _formatLongDuration(Duration(milliseconds: totalDurationMs))
        : currentContextType.isNotEmpty
            ? 'live from Spotify'
            : 'live queue';
    return 'EmoTune - $count $itemLabel - $lengthLabel';
  }

  bool _isCurrentQueueItem(PlayerProvider player, Map<String, dynamic> item, int index) {
    final currentTrack = player.currentTrack;
    if (currentTrack == null) {
      return false;
    }

    final currentUri = currentTrack['uri']?.toString() ?? '';
    final itemUri = item['uri']?.toString() ?? '';
    final currentId = currentTrack['id']?.toString() ?? '';
    final itemId = item['id']?.toString() ?? '';

    if (currentUri.isNotEmpty && currentUri == itemUri) {
      return true;
    }
    if (currentId.isNotEmpty && currentId == itemId) {
      return true;
    }
    return player.currentIndex == index;
  }

  Future<void> _toggleFavorite(
    BuildContext context,
    PlayerProvider player,
    Map<String, dynamic> track,
  ) async {
    try {
      final result = await player.toggleFavoriteForCurrentTrack();
      if (!context.mounted) {
        return;
      }
      final message = switch (result) {
        true => 'Added to favorites.',
        false => 'Removed from favorites.',
        _ => 'Could not update favorites.',
      };
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: result == null
              ? Colors.redAccent
              : const Color(0xFF9EFF65),
        ),
      );
    } catch (_) {
      if (!context.mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Error adding to favorites')),
      );
    }
  }

  static Color _blendWithBlack(Color color, double amount) {
    return Color.lerp(color, Colors.black, amount) ?? color;
  }

  static String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  static String _formatLongDuration(Duration duration) {
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    if (hours > 0) {
      return '${hours}h ${minutes}m';
    }
    if (minutes > 0) {
      return '${minutes}m';
    }
    return '${duration.inSeconds}s';
  }
}

class _HeaderArtwork extends StatelessWidget {
  const _HeaderArtwork({
    required this.imageUrl,
    required this.accentColor,
  });

  final String imageUrl;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 128,
      height: 128,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.24),
            blurRadius: 24,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: imageUrl.isNotEmpty
            ? CachedNetworkImage(
                imageUrl: imageUrl,
                fit: BoxFit.cover,
              )
            : DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      FullPlayerScreen._blendWithBlack(accentColor, 0.15),
                      FullPlayerScreen._blendWithBlack(accentColor, 0.45),
                      const Color(0xFF111111),
                    ],
                  ),
                ),
                child: const Icon(
                  Icons.graphic_eq_rounded,
                  color: Colors.white,
                  size: 52,
                ),
              ),
      ),
    );
  }
}

class _SessionPlanCard extends StatelessWidget {
  const _SessionPlanCard({required this.player});

  final PlayerProvider player;

  @override
  Widget build(BuildContext context) {
    final sessionLabel = player.sessionPlan?['label']?.toString().trim().isNotEmpty == true
        ? player.sessionPlan!['label'].toString().trim()
        : (player.outcomeLabel?.trim().isNotEmpty == true
            ? player.outcomeLabel!.trim()
            : 'Mood Session');
    final sessionDescription =
        player.sessionPlan?['description']?.toString().trim().isNotEmpty == true
            ? player.sessionPlan!['description'].toString().trim()
            : (player.outcomeDescription?.trim().isNotEmpty == true
                ? player.outcomeDescription!.trim()
                : 'EmoTune is shaping this queue around your selected lane.');
    final progressLabel = player.sessionTargetDuration.inSeconds > 0
        ? '${FullPlayerScreen._formatLongDuration(player.sessionProgressDuration)} / ${FullPlayerScreen._formatLongDuration(player.sessionTargetDuration)}'
        : 'Untimed support lane';
    final nextCheckIn = player.sessionNextCheckInTrack;
    final chips = <String>[
      _familiarityLabel(player.familiarity),
      if (player.preferInstrumental) 'Instrumental bias',
      if (!player.trainOnThisSession) 'Learning paused',
      if (player.isSessionComplete) 'Check-ins complete',
    ];

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: AppColors.accent.withOpacity(0.18),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.tune_rounded,
                  color: AppColors.accent,
                  size: 18,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sessionLabel,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      sessionDescription,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.68),
                        fontSize: 11,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (player.hasActiveSessionPlan) ...[
            const SizedBox(height: 14),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: player.sessionProgressFraction,
                minHeight: 6,
                backgroundColor: Colors.white12,
                valueColor: const AlwaysStoppedAnimation<Color>(AppColors.accent),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: Text(
                    progressLabel,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.78),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (nextCheckIn != null)
                  Text(
                    player.isSessionComplete
                        ? 'No more check-ins'
                        : 'Next check-in: song $nextCheckIn',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.62),
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
              ],
            ),
          ],
          if (chips.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: chips
                  .map(
                    (chip) => Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.black.withOpacity(0.18),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(color: Colors.white10),
                      ),
                      child: Text(
                        chip,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.84),
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }

  String _familiarityLabel(String familiarity) {
    switch (familiarity) {
      case 'familiar':
        return 'More familiar';
      case 'discovery':
        return 'More discovery';
      default:
        return 'Balanced taste';
    }
  }
}

class _ControlStrip extends StatelessWidget {
  const _ControlStrip({
    required this.player,
    required this.track,
    required this.onFavorite,
  });

  final PlayerProvider player;
  final Map<String, dynamic> track;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) {
    final favoriteIcon = player.isCurrentTrackFavorite
        ? Icons.favorite_rounded
        : Icons.favorite_border_rounded;
    final repeatIcon = player.isRepeatTrackMode
        ? Icons.repeat_one_rounded
        : Icons.repeat_rounded;
    final repeatTooltip = switch (player.repeatMode) {
      'context' => 'Repeat all songs',
      'track' => 'Repeat this song',
      _ => 'Repeat off',
    };
    final shuffleTooltip = player.isShuffleEnabled
        ? 'Shuffle on'
        : 'Shuffle off';

    return Row(
      children: [
        GestureDetector(
          onTap: player.togglePlayPause,
          child: Container(
            width: 58,
            height: 58,
            decoration: const BoxDecoration(
              color: AppColors.accent,
              shape: BoxShape.circle,
            ),
            child: Icon(
              player.isLoading
                  ? Icons.hourglass_empty_rounded
                  : player.isPlaying
                      ? Icons.pause_rounded
                      : Icons.play_arrow_rounded,
              color: Colors.black,
              size: 34,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.08),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Colors.white.withOpacity(0.10)),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: track['image'] != null && track['image'].toString().isNotEmpty
                ? CachedNetworkImage(
                    imageUrl: track['image'].toString(),
                    fit: BoxFit.cover,
                  )
                : const Icon(
                    Icons.music_note_rounded,
                    color: Colors.white,
                    size: 18,
                  ),
          ),
        ),
        const SizedBox(width: 18),
        _IconChip(
          icon: Icons.shuffle_rounded,
          onTap: player.toggleShuffle,
          active: player.isShuffleEnabled,
          tooltip: shuffleTooltip,
        ),
        const SizedBox(width: 14),
        _IconChip(
          icon: favoriteIcon,
          onTap: onFavorite,
          active: player.isCurrentTrackFavorite,
          tooltip: player.isCurrentTrackFavorite
              ? 'Remove from favorites'
              : 'Add to favorites',
        ),
        const SizedBox(width: 14),
        _IconChip(
          icon: Icons.skip_previous_rounded,
          onTap: player.previous,
          active: false,
          tooltip: 'Previous song',
        ),
        const SizedBox(width: 14),
        _IconChip(
          icon: Icons.skip_next_rounded,
          onTap: player.next,
          active: false,
          tooltip: 'Next song',
        ),
        const SizedBox(width: 14),
        _IconChip(
          icon: repeatIcon,
          onTap: player.cycleRepeatMode,
          active: player.isRepeatEnabled,
          tooltip: repeatTooltip,
        ),
      ],
    );
  }
}

class _IconChip extends StatelessWidget {
  const _IconChip({
    required this.icon,
    required this.onTap,
    required this.active,
    this.tooltip,
  });

  final IconData icon;
  final VoidCallback? onTap;
  final bool active;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.accent : Colors.white.withOpacity(0.88);
    return Tooltip(
      message: tooltip ?? '',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Icon(
          icon,
          color: color,
          size: 24,
        ),
      ),
    );
  }
}

class _QueueRow extends StatelessWidget {
  const _QueueRow({
    required this.track,
    required this.index,
    required this.isCurrent,
    required this.isPlaying,
    required this.emotionColor,
    required this.onTap,
  });

  final Map<String, dynamic> track;
  final int index;
  final bool isCurrent;
  final bool isPlaying;
  final Color emotionColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final image = track['image']?.toString() ?? '';
    final title = track['name']?.toString() ?? '';
    final subtitle = _subtitle();
    final duration = _durationLabel();

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 2),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(
          color: isCurrent ? Colors.white.withOpacity(0.12) : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 20,
              child: Text(
                '${index + 1}',
                style: TextStyle(
                  color: isCurrent
                      ? Colors.white
                      : Colors.white.withOpacity(0.72),
                  fontSize: 14,
                  fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
            ),
            const SizedBox(width: 14),
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(6),
                color: Colors.white.withOpacity(0.06),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: image.isNotEmpty
                    ? CachedNetworkImage(
                        imageUrl: image,
                        fit: BoxFit.cover,
                      )
                    : Container(
                        color: FullPlayerScreen._blendWithBlack(emotionColor, 0.55),
                        child: const Icon(
                          Icons.music_note_rounded,
                          color: Colors.white,
                          size: 18,
                        ),
                      ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: isCurrent ? Colors.white : Colors.white.withOpacity(0.92),
                      fontSize: 16,
                      fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: isCurrent
                          ? AppColors.accent
                          : Colors.white.withOpacity(0.62),
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            if (isCurrent)
              Icon(
                isPlaying ? Icons.volume_up_rounded : Icons.pause_circle_filled_rounded,
                color: AppColors.accent,
                size: 20,
              )
            else
              Text(
                duration,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.72),
                  fontSize: 14,
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _subtitle() {
    final artist = track['artist']?.toString().trim() ?? '';
    final itemType = track['item_type']?.toString() ?? 'track';

    if (itemType == 'playlist') {
      return artist.isNotEmpty ? '$artist playlist' : 'Playlist';
    }
    if (itemType == 'artist') {
      return artist.isNotEmpty ? '$artist radio' : 'Artist radio';
    }
    return artist.isNotEmpty ? artist : 'EmoTune';
  }

  String _durationLabel() {
    final itemType = track['item_type']?.toString() ?? 'track';
    if (itemType != 'track') {
      return itemType;
    }
    final durationMs = (track['duration_ms'] as num?)?.toInt() ?? 0;
    if (durationMs <= 0) {
      return '--:--';
    }
    return FullPlayerScreen._formatDuration(
      Duration(milliseconds: durationMs),
    );
  }
}

class _ContextLoadingCard extends StatelessWidget {
  const _ContextLoadingCard({required this.track});

  final Map<String, dynamic> track;

  @override
  Widget build(BuildContext context) {
    final itemType = track['item_type']?.toString() ?? 'playlist';
    final name = track['name']?.toString() ?? 'Spotify playlist';
    final label = itemType == 'playlist' ? 'playlist' : itemType;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withOpacity(0.10)),
      ),
      child: Row(
        children: [
          const SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(
              strokeWidth: 2.2,
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              'Opening $name. EmoTune is waiting for Spotify to return the $label tracks.',
              style: TextStyle(
                color: Colors.white.withOpacity(0.86),
                fontSize: 13,
                height: 1.35,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetaText extends StatelessWidget {
  const _MetaText(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        color: Colors.white.withOpacity(0.56),
        fontSize: 12,
        fontWeight: FontWeight.w600,
      ),
    );
  }
}
