import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:provider/provider.dart';
import '../../providers/player_provider.dart';
import '../../theme/app_theme.dart';

class TrackCard extends StatelessWidget {
  final Map<String, dynamic> track;
  final VoidCallback onTap;
  final String emotion;

  const TrackCard({
    super.key,
    required this.track,
    required this.onTap,
    required this.emotion,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final image = track['image'] as String?;
    final emotionColor = AppColors.emotionColors[emotion] ?? AppColors.accent;
    final subtitle = _subtitleText();
    final staticPickLabel = _staticPickLabel();
    final itemType = track['item_type']?.toString().trim().toLowerCase() ?? 'track';
    // A music.md song Spotify could not resolve: it keeps its slot so the
    // list matches the therapist's, but it can only be searched for.
    final playable = PlayerProvider.isPlayable(track);
    final note = !playable ? 'Open in Spotify' : null;
    // Its id is a placeholder, so a heart would favorite nothing.
    final canFavorite = itemType == 'track' && playable;
    final player = canFavorite ? context.watch<PlayerProvider>() : null;
    final isFavorite = player?.isFavoriteTrack(track) ?? false;

    return Semantics(
      hint: !playable ? 'Not found on Spotify. Opens a Spotify search.' : null,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: isDark ? AppColors.darkCard : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isDark ? AppColors.darkBorder : Colors.grey.shade200,
            ),
            boxShadow: [
              BoxShadow(
                color: emotionColor.withValues(alpha: 0.1),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Album art
                Expanded(
                  child: Stack(
                    children: [
                      SizedBox(
                        width: double.infinity,
                        child: image != null && image.isNotEmpty
                            ? CachedNetworkImage(
                                imageUrl: image,
                                fit: BoxFit.cover,
                                placeholder: (_, __) => Container(
                                  color: emotionColor.withValues(alpha: 0.2),
                                  child: Icon(Icons.music_note,
                                      color: emotionColor, size: 40),
                                ),
                                errorWidget: (_, __, ___) => Container(
                                  color: emotionColor.withValues(alpha: 0.2),
                                  child: Icon(Icons.music_note,
                                      color: emotionColor, size: 40),
                                ),
                              )
                            : Container(
                                color: emotionColor.withValues(alpha: 0.2),
                                child: Center(
                                  child: Icon(Icons.music_note,
                                      color: emotionColor, size: 40),
                                ),
                              ),
                      ),
                      // Play button overlay
                      Positioned(
                        bottom: 8,
                        right: 8,
                        child: Container(
                          width: 32,
                          height: 32,
                          decoration: const BoxDecoration(
                            color: AppColors.accent,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                              playable ? Icons.play_arrow : Icons.open_in_new,
                              color: Colors.black,
                              size: playable ? 20 : 17),
                        ),
                      ),
                      if (staticPickLabel != null)
                        Positioned(
                          top: 8,
                          left: 8,
                          child: _CardBadge(
                            label: staticPickLabel,
                            background: AppColors.gradientEnd,
                            // White on the lime badge was about 1.2:1 and
                            // hard to read; black is about 16:1.
                            foreground: Colors.black,
                          ),
                        ),
                      if (canFavorite)
                        Positioned(
                          top: 8,
                          right: 8,
                          child: Semantics(
                            button: true,
                            label: isFavorite
                                ? 'Remove from favorites'
                                : 'Add to favorites',
                            child: GestureDetector(
                              onTap: () => player!
                                  .toggleFavoriteForTrack(track, emotion: emotion),
                              child: Container(
                                width: 26,
                                height: 26,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.32),
                                  shape: BoxShape.circle,
                                ),
                                child: Icon(
                                  isFavorite
                                      ? Icons.favorite
                                      : Icons.favorite_border,
                                  size: 14,
                                  color: isFavorite
                                      ? const Color(0xFFE2645B)
                                      : Colors.white,
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),

                // Track info
                Padding(
                  padding: const EdgeInsets.all(10),
                  child: Column(
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
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: isDark ? Colors.white54 : Colors.black54,
                          fontSize: 11,
                        ),
                      ),
                      if (note != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          note,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: !playable
                                ? context.emoColors.accentText
                                : context.emoColors.textSecondary,
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// The picks that are the same for everyone: the docs/music.md list that
  /// "Balanced" opens with, and the built-in playlists served when Spotify has
  /// nothing to give.
  String? _staticPickLabel() {
    final recommendationSource = track['recommendation_source']?.toString() ?? '';
    if (track['is_music_doc_pick'] == true ||
        recommendationSource == 'music_md_playlist') {
      return 'EmoTune pick';
    }
    if (recommendationSource == 'curated_fallback') {
      return 'Built-in list';
    }
    return null;
  }

  String _subtitleText() {
    final itemType = track['item_type']?.toString() ?? 'track';
    final recommendationSource = track['recommendation_source']?.toString() ?? '';
    final artist = track['artist']?.toString().trim() ?? '';

    if (recommendationSource == 'curated_fallback') {
      return itemType == 'playlist' ? 'Tap to open playlist' : 'Tap to play in app';
    }
    if (artist.toLowerCase() == 'open in spotify') {
      return 'Tap to play in app';
    }
    return artist.isNotEmpty ? artist : 'Tap to play in app';
  }
}

class _CardBadge extends StatelessWidget {
  const _CardBadge({
    required this.label,
    required this.background,
    required this.foreground,
  });

  final String label;
  final Color background;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          color: foreground,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}
