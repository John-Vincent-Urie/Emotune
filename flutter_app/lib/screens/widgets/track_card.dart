import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
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

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1A1A1A) : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isDark ? const Color(0xFF2A2A2A) : Colors.grey.shade200,
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
                        child: const Icon(Icons.play_arrow,
                            color: Colors.black, size: 20),
                      ),
                    ),
                    if (track['is_preferred'] == true)
                      Positioned(
                        top: 8,
                        left: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.amber,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text('★ Fav',
                              style: TextStyle(
                                  fontSize: 10,
                                  color: Colors.black,
                                  fontWeight: FontWeight.bold)),
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
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
