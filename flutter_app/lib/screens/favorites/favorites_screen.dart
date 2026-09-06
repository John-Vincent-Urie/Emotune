import 'package:flutter/material.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../providers/player_provider.dart';
import 'package:provider/provider.dart';
import '../home/full_player_screen.dart';

class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  List<dynamic> _favorites = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final favs = await ApiService.getFavorites();
      setState(() {
        _favorites = favs;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Favorites ❤️'),
        backgroundColor: isDark ? Colors.black : Colors.white,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _favorites.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.favorite_border,
                          size: 60,
                          color: isDark ? Colors.white12 : Colors.black12),
                      const SizedBox(height: 16),
                      Text('No favorites yet',
                          style: TextStyle(
                              color: isDark ? Colors.white54 : Colors.black54)),
                      const SizedBox(height: 8),
                      Text('Tap ❤️ on any song to save it',
                          style: TextStyle(
                              color: isDark ? Colors.white38 : Colors.black38,
                              fontSize: 12)),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _favorites.length,
                  itemBuilder: (ctx, i) {
                    final fav = _favorites[i];
                    return _FavoriteItem(
                      track: fav,
                      onDelete: () => _delete(fav['spotify_track_id']),
                      onPlay: () => _play(fav),
                    );
                  },
                ),
    );
  }

  Future<void> _delete(String trackId) async {
    await ApiService.removeFavorite(trackId);
    _load();
  }

  Future<void> _play(Map<String, dynamic> fav) async {
    final emotion = _favoriteEmotion(fav);
    final track = {
      'id': fav['spotify_track_id'],
      'name': fav['track_name'],
      'artist': fav['artist_name'],
      'album': fav['album_name'],
      'image': fav['album_image'],
      'preview_url': fav['preview_url'],
      'duration_ms': fav['duration_ms'],
      'spotify_url':
          'https://open.spotify.com/track/${fav['spotify_track_id']}',
      'uri': 'spotify:track:${fav['spotify_track_id']}',
    };
    final hasPreview =
        track['preview_url']?.toString().trim().isNotEmpty == true;
    context.read<PlayerProvider>().loadPlaylist(
          [track],
          emotion.isEmpty ? 'mixed' : emotion,
          autoplay: false,
        );
    await context.read<PlayerProvider>().playTrackAtIndex(
          0,
          preferInstantPreview: hasPreview,
        );
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
}

/// The emotion this track was hearted under, or '' when it predates emotion
/// tagging. "More familiar" only replays favorites that carry one.
String _favoriteEmotion(dynamic favorite) =>
    favorite is Map ? (favorite['emotion']?.toString().trim().toLowerCase() ?? '') : '';

class _FavoriteItem extends StatelessWidget {
  final dynamic track;
  final VoidCallback onDelete;
  final VoidCallback onPlay;

  const _FavoriteItem({
    required this.track,
    required this.onDelete,
    required this.onPlay,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final image = track['album_image'] as String?;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1A1A1A) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? const Color(0xFF2A2A2A) : Colors.grey.shade200),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              width: 56,
              height: 56,
              child: image != null && image.isNotEmpty
                  ? Image.network(image, fit: BoxFit.cover)
                  : Container(
                      color: AppColors.accent.withValues(alpha: 0.2),
                      child:
                          const Icon(Icons.music_note, color: AppColors.accent),
                    ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  track['track_name'] ?? '',
                  style: TextStyle(
                      color: isDark ? Colors.white : Colors.black87,
                      fontWeight: FontWeight.bold,
                      fontSize: 14),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  track['artist_name'] ?? '',
                  style: TextStyle(
                      color: isDark ? Colors.white54 : Colors.black54,
                      fontSize: 12),
                ),
                const SizedBox(height: 6),
                _EmotionTag(emotion: _favoriteEmotion(track), isDark: isDark),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.play_circle,
                color: AppColors.accent, size: 32),
            onPressed: onPlay,
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline,
                color: Colors.redAccent, size: 22),
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}

/// Shows which emotion a favorite belongs to, so it is clear which songs
/// "More familiar" will replay -- and which ones are still untagged because
/// they were hearted before emotions were recorded.
class _EmotionTag extends StatelessWidget {
  const _EmotionTag({required this.emotion, required this.isDark});

  final String emotion;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final tagged = emotion.isNotEmpty;
    final color = tagged
        ? (AppColors.emotionColors[emotion] ?? AppColors.accent)
        : (isDark ? Colors.white38 : Colors.black38);
    final label = tagged ? emotion.toUpperCase() : 'NO EMOTION YET';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: tagged ? 0.15 : 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: tagged ? 1 : 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}
