import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/player_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotune_page_header.dart';
import '../home/full_player_screen.dart';
import '../widgets/track_card.dart';

class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key, this.onExploreDiscover});

  /// Lets the empty state's "Explore Discover" button jump to that tab --
  /// wired by [MainShell], since the two screens are siblings.
  final VoidCallback? onExploreDiscover;

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  @override
  void initState() {
    super.initState();
    // The tab lives inside MainShell's IndexedStack, so initState runs once
    // for the life of the app. Everything after this first fetch comes from
    // PlayerProvider's FavoritesManager, which every heart toggle updates.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context.read<PlayerProvider>().refreshFavorites();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // Favoriting from any card (here, Home or Discover) goes through
    // PlayerProvider's shared FavoritesManager, which holds the favorite
    // records themselves -- so a heart tapped anywhere shows up in this grid
    // immediately, with no refetch and no app restart.
    final player = context.watch<PlayerProvider>();
    final favorites = player.favoriteTracks;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            const EmoTunePageHeader(title: 'Favorites'),
            Expanded(
              child: !player.favoritesLoaded && favorites.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : favorites.isEmpty
                      ? _EmptyFavorites(onExplore: widget.onExploreDiscover)
                      : RefreshIndicator(
                          onRefresh: () => context
                              .read<PlayerProvider>()
                              .refreshFavorites(),
                          child: GridView.builder(
                            // Keeps pull-to-refresh working when the grid is
                            // too short to scroll on its own.
                            physics: const AlwaysScrollableScrollPhysics(),
                            padding: const EdgeInsets.fromLTRB(20, 4, 20, 18),
                            gridDelegate:
                                const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              childAspectRatio: 0.85,
                              crossAxisSpacing: 12,
                              mainAxisSpacing: 12,
                            ),
                            itemCount: favorites.length,
                            itemBuilder: (ctx, i) {
                              final fav = favorites[i];
                              return TrackCard(
                                track: _trackFromFavorite(fav),
                                emotion: _favoriteEmotion(fav),
                                onTap: () => _play(fav),
                              );
                            },
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Map<String, dynamic> _trackFromFavorite(Map fav) {
    return {
      'id': fav['spotify_track_id'],
      'name': fav['track_name'],
      'artist': fav['artist_name'],
      'album': fav['album_name'] ?? '',
      'image': fav['album_image'] ?? '',
      'preview_url': fav['preview_url'],
      'duration_ms': fav['duration_ms'] ?? 0,
      'spotify_url':
          'https://open.spotify.com/track/${fav['spotify_track_id']}',
      'uri': 'spotify:track:${fav['spotify_track_id']}',
      'item_type': 'track',
    };
  }

  Future<void> _play(Map fav) async {
    final emotion = _favoriteEmotion(fav);
    final track = _trackFromFavorite(fav);
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
/// tagging.
String _favoriteEmotion(dynamic favorite) => favorite is Map
    ? (favorite['emotion']?.toString().trim().toLowerCase() ?? '')
    : '';

class _EmptyFavorites extends StatefulWidget {
  const _EmptyFavorites({this.onExplore});

  final VoidCallback? onExplore;

  @override
  State<_EmptyFavorites> createState() => _EmptyFavoritesState();
}

class _EmptyFavoritesState extends State<_EmptyFavorites>
    with SingleTickerProviderStateMixin {
  late final AnimationController _beat;

  @override
  void initState() {
    super.initState();
    _beat = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.of(context).disableAnimations) {
      _beat.stop();
    } else {
      _beat.repeat();
    }
  }

  @override
  void dispose() {
    _beat.dispose();
    super.dispose();
  }

  double _heartbeatScale(double t) {
    if (t < 0.15) return 1.0 + 0.14 * (t / 0.15);
    if (t < 0.30) return 1.14 - 0.14 * ((t - 0.15) / 0.15);
    if (t < 0.45) return 1.0 + 0.08 * ((t - 0.30) / 0.15);
    if (t < 0.60) return 1.08 - 0.08 * ((t - 0.45) / 0.15);
    return 1.0;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final heartIcon = Icon(
      Icons.favorite_border,
      size: 64,
      color: colors.textSecondary.withValues(alpha: 0.55),
    );

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 34),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            reduceMotion
                ? heartIcon
                : AnimatedBuilder(
                    animation: _beat,
                    builder: (context, child) => Transform.scale(
                      scale: _heartbeatScale(_beat.value),
                      child: child,
                    ),
                    child: heartIcon,
                  ),
            const SizedBox(height: 14),
            Text(
              'No favorites yet',
              style: TextStyle(
                color: colors.textPrimary,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 6),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Tap ',
                  style: TextStyle(color: colors.textSecondary, fontSize: 13),
                ),
                const Icon(Icons.favorite, size: 13, color: Color(0xFFE2645B)),
                Text(
                  ' on any song to save it',
                  style: TextStyle(color: colors.textSecondary, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: widget.onExplore,
              style: OutlinedButton.styleFrom(
                foregroundColor: colors.textPrimary,
                side: BorderSide(color: colors.divider),
                padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(22),
                ),
              ),
              child: const Text(
                'Explore Discover',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
