import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../providers/player_provider.dart';
import '../../theme/app_theme.dart';
import '../home/full_player_screen.dart';

class MiniPlayer extends StatelessWidget {
  const MiniPlayer({super.key});

  @override
  Widget build(BuildContext context) {
    final player = context.watch<PlayerProvider>();
    final track = player.currentTrack;
    if (track == null) return const SizedBox.shrink();

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final progress = player.duration.inSeconds > 0
        ? player.position.inSeconds / player.duration.inSeconds
        : 0.0;
    // A failure used to leave only the artist here, so a silent player looked
    // fine. Point at the full player, which explains the error.
    final playbackStatus = player.errorMessage != null
        ? "Couldn't play · tap for details"
        : _shouldShowPlaybackStatus(player)
            ? player.playbackStatusShortLabel
            : '';
    final imageUrl = track['image']?.toString().trim() ?? '';

    return GestureDetector(
      onTap: () {
        showModalBottomSheet(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (_) => const FullPlayerScreen(),
        );
      },
      child: Container(
        height: 70,
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(
          color: isDark ? AppColors.darkCard : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isDark ? AppColors.darkBorder : Colors.grey.shade200,
          ),
          boxShadow: [
            BoxShadow(
              color: AppColors.accent.withValues(alpha: 0.1),
              blurRadius: 10,
            ),
          ],
        ),
        child: Column(
          children: [
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    // Album art
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: SizedBox(
                        width: 40,
                        height: 40,
                        // Without placeholder/errorWidget a reload or a failed
                        // fetch drew nothing, which on the dark card showed
                        // up as a black square.
                        child: imageUrl.isNotEmpty
                            ? CachedNetworkImage(
                                imageUrl: imageUrl,
                                fit: BoxFit.cover,
                                useOldImageOnUrlChange: true,
                                placeholder: (_, __) => const _ArtFallback(),
                                errorWidget: (_, __, ___) =>
                                    const _ArtFallback(),
                              )
                            : const _ArtFallback(),
                      ),
                    ),
                    const SizedBox(width: 12),
                    
                    // Track info
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            track['name'] ?? '',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: isDark ? Colors.white : Colors.black87,
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                            ),
                          ),
                          Text(
                            [
                              track['artist']?.toString() ?? '',
                              playbackStatus,
                            ].where((part) => part.trim().isNotEmpty).join('  •  '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: isDark ? Colors.white54 : Colors.black54,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                    // Controls
                    IconButton(
                      icon: Icon(Icons.skip_previous,
                          color: isDark ? Colors.white : Colors.black87),
                      tooltip: 'Previous track',
                      onPressed: player.previous,
                      iconSize: 20,
                    ),
                    Semantics(
                      button: true,
                      label: player.isPlaying ? 'Pause' : 'Play',
                      child: GestureDetector(
                        onTap: player.togglePlayPause,
                        child: Container(
                          width: 34,
                          height: 34,
                          decoration: const BoxDecoration(
                            gradient: AppColors.buttonGradient,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            player.isPlaying ? Icons.pause : Icons.play_arrow,
                            color: Colors.black,
                            size: 18,
                          ),
                        ),
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.skip_next,
                          color: isDark ? Colors.white : Colors.black87),
                      tooltip: 'Next track',
                      onPressed: player.next,
                      iconSize: 20,
                    ),
                  ],
                ),
              ),
            ),
            // Progress bar
            LinearProgressIndicator(
              value: progress.clamp(0.0, 1.0),
              backgroundColor: isDark ? Colors.white12 : Colors.black12,
              valueColor: const AlwaysStoppedAnimation<Color>(AppColors.accent),
              minHeight: 2,
            ),
          ],
        ),
      ),
    );
  }

  bool _shouldShowPlaybackStatus(PlayerProvider player) {
    if (player.errorMessage != null) {
      return false;
    }
    return switch (player.playbackStatusCode) {
      'spotify_background_unavailable' => false,
      'not_directly_playable' => false,
      'preview_error' => false,
      _ => true,
    };
  }
}

class _ArtFallback extends StatelessWidget {
  const _ArtFallback();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.accent.withValues(alpha: 0.3),
      child: const Icon(Icons.music_note, size: 20),
    );
  }
}
