import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/spotify_connection_controller.dart';
import '../../providers/auth_provider.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../providers/theme_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../widgets/recommendation_session_controls.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  List<dynamic> _artists = [];
  List<dynamic> _searchResults = [];
  final _artistSearchCtrl = TextEditingController();
  final _spotifyConnection = SpotifyConnectionController();
  bool _isSavingArtists = false;

  @override
  void initState() {
    super.initState();
    _spotifyConnection.addListener(_onSpotifyConnectionChanged);
    _loadArtists();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final user = Provider.of<AuthProvider>(context).user;
    _syncArtistsFromUser(user);
  }

  void _loadArtists() {
    final auth = context.read<AuthProvider>();
    final user = auth.user;
    if (user != null) {
      setState(() {
        _artists = List.from(user['preferred_artists'] ?? []);
      });
    }
  }

  void _syncArtistsFromUser(Map<String, dynamic>? user) {
    if (_isSavingArtists) {
      return;
    }

    final preferredArtists = List<String>.from(
      user?['preferred_artists'] ?? const <String>[],
    );
    if (listEquals(_artists.cast<String>(), preferredArtists)) {
      return;
    }
    _artists = preferredArtists;
  }

  @override
  void dispose() {
    _spotifyConnection.removeListener(_onSpotifyConnectionChanged);
    _spotifyConnection.dispose();
    _artistSearchCtrl.dispose();
    super.dispose();
  }

  void _onSpotifyConnectionChanged() {
    if (mounted) {
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final themeProvider = context.watch<ThemeProvider>();
    final studio = context.watch<RecommendationStudioProvider>();
    final user = auth.user;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (user == null) {
      return Scaffold(
        body: Center(
          child: ElevatedButton(
            onPressed: () => Navigator.pushReplacementNamed(context, '/login'),
            child: const Text('Login'),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Profile'),
        actions: [
          IconButton(
            icon:
                Icon(themeProvider.isDark ? Icons.light_mode : Icons.dark_mode),
            onPressed: themeProvider.toggleTheme,
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await auth.logout();
              if (!context.mounted) return;
              Navigator.pushReplacementNamed(context, '/welcome');
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Profile header
            _ProfileHeader(user: user, isDark: isDark),

            const SizedBox(height: 32),

            // Theme toggle
            _sectionTitle('Appearance', isDark),
            const SizedBox(height: 12),
            _card(
              isDark,
              child: Row(
                children: [
                  Icon(
                    themeProvider.isDark ? Icons.dark_mode : Icons.light_mode,
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    themeProvider.isDark ? 'Dark Mode' : 'Light Mode',
                    style: TextStyle(
                        color: isDark ? Colors.white : Colors.black87),
                  ),
                  const Spacer(),
                  Switch(
                    value: themeProvider.isDark,
                    onChanged: (_) => themeProvider.toggleTheme(),
                    activeThumbColor: AppColors.accent,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Preferred Artists
            _sectionTitle('Preferred Artists', isDark),
            const SizedBox(height: 8),
            Text('Artists we\'ll prioritize in recommendations',
                style: TextStyle(
                    color: isDark ? Colors.white54 : Colors.black54,
                    fontSize: 12)),
            const SizedBox(height: 12),

            // Artist search
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _artistSearchCtrl,
                    style: TextStyle(
                        color: isDark ? Colors.white : Colors.black87),
                    enabled: !_isSavingArtists,
                    decoration: const InputDecoration(
                      hintText: 'Search an artist...',
                      prefixIcon: Icon(Icons.search),
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    ),
                    onChanged: _searchArtists,
                  ),
                ),
              ],
            ),

            if (_searchResults.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                decoration: BoxDecoration(
                  color: isDark ? AppColors.darkCard : Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                      color: isDark
                          ? AppColors.darkBorder
                          : Colors.grey.shade200),
                ),
                child: Column(
                  children: _searchResults.take(5).map<Widget>((artist) {
                    final name = artist['name'] as String;
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundImage: artist['image'] != null
                            ? NetworkImage(artist['image'])
                            : null,
                        backgroundColor: AppColors.accent.withValues(alpha: 0.2),
                        child: artist['image'] == null
                            ? Text(name[0],
                                style: const TextStyle(color: AppColors.accent))
                            : null,
                      ),
                      title: Text(name,
                          style: TextStyle(
                              color: isDark ? Colors.white : Colors.black87)),
                      trailing: _artists.contains(name)
                          ? const Icon(Icons.check, color: AppColors.accent)
                          : IconButton(
                              icon: const Icon(Icons.add,
                                  color: AppColors.accent),
                              onPressed: _isSavingArtists
                                  ? null
                                  : () => _addArtist(name),
                            ),
                    );
                  }).toList(),
                ),
              ),
            ],

            const SizedBox(height: 12),

            // Current artists
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _artists.map<Widget>((a) {
                return Chip(
                  label: Text(a.toString()),
                  backgroundColor: AppColors.accent.withValues(alpha: 0.15),
                  labelStyle: const TextStyle(color: AppColors.accent),
                  deleteIcon: const Icon(Icons.close,
                      size: 16, color: AppColors.accent),
                  onDeleted: _isSavingArtists
                      ? null
                      : () => _removeArtist(a.toString()),
                );
              }).toList(),
            ),

            const SizedBox(height: 24),

            _sectionTitle('Privacy & Personalization', isDark),
            const SizedBox(height: 12),
            _card(
              isDark,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.auto_awesome,
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Mood-based personalization',
                          style: TextStyle(
                            color: isDark ? Colors.white : Colors.black87,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'When this is on, EmoTune can learn from your listening sessions to improve future recommendations.',
                          style: TextStyle(
                            color: isDark ? Colors.white54 : Colors.black54,
                            fontSize: 12,
                            height: 1.4,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Switch(
                    value: user['personalization_opt_in'] != false,
                    onChanged: _updatePersonalizationOptIn,
                    activeThumbColor: AppColors.accent,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            _sectionTitle('Recommendation Studio', isDark),
            const SizedBox(height: 8),
            Text(
              'These recommendation settings apply across Home and Discover, so you only need to tune them once here.',
              style: TextStyle(
                color: isDark ? Colors.white54 : Colors.black54,
                fontSize: 12,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 12),
            RecommendationSessionControls(
              sessionLengthMinutes: studio.sessionLengthMinutes,
              onSessionLengthChanged: studio.setSessionLengthMinutes,
              familiarity: studio.familiarity,
              onFamiliarityChanged: studio.setFamiliarity,
              preferInstrumental: studio.preferInstrumental,
              onPreferInstrumentalChanged: studio.setPreferInstrumental,
              trainOnThisSession: studio.trainOnThisSession,
              onTrainOnThisSessionChanged: studio.setTrainOnThisSession,
              title: 'Recommendation Studio',
              subtitle:
                  'Shape the session timing and taste controls that EmoTune should use by default.',
            ),

            const SizedBox(height: 24),

            // Account settings
            _sectionTitle('Account', isDark),
            const SizedBox(height: 12),

            _card(
              isDark,
              child: Column(
                children: [
                  _settingsTile(
                    Icons.person_outline,
                    'Edit Profile',
                    () => _showEditProfile(context, user),
                    isDark,
                  ),
                  _divider(isDark),
                  _settingsTile(
                    Icons.lock_outline,
                    'Change Password',
                    () => _showChangePassword(context),
                    isDark,
                  ),
                  _divider(isDark),
                  _settingsTile(
                    Icons.music_note,
                    _spotifyConnection.isConnecting
                        ? 'Connecting Spotify...'
                        : 'Connect Spotify',
                    _spotifyConnection.isConnecting
                        ? null
                        : () => _spotifyConnection.connect(context),
                    isDark,
                    trailing: _spotifyConnection.isConnecting
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : user['is_spotify_connected'] == true
                            ? const Icon(Icons.check_circle,
                                color: Colors.green, size: 18)
                            : null,
                  ),
                  if (user['is_spotify_connected'] == true) ...[
                    _divider(isDark),
                    _settingsTile(
                      Icons.link_off,
                      _spotifyConnection.isDisconnecting
                          ? 'Disconnecting Spotify...'
                          : 'Disconnect Spotify',
                      _spotifyConnection.isDisconnecting
                          ? null
                          : () => _spotifyConnection.disconnect(context),
                      isDark,
                      trailing: _spotifyConnection.isDisconnecting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.link_off, size: 18),
                    ),
                  ],
                ],
              ),
            ),

            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Future<void> _searchArtists(String query) async {
    if (query.length < 2) {
      setState(() => _searchResults = []);
      return;
    }
    try {
      final results = await ApiService.searchArtists(query);
      setState(() {
        _searchResults = results;
      });
    } catch (e) {
      setState(() => _searchResults = []);
    }
  }

  Future<void> _addArtist(String artist) async {
    if (_artists.contains(artist)) {
      _artistSearchCtrl.clear();
      setState(() => _searchResults = []);
      return;
    }

    final previousArtists = List<String>.from(_artists.cast<String>());
    final nextArtists = [...previousArtists, artist];
    _artistSearchCtrl.clear();
    setState(() => _searchResults = []);
    await _persistArtists(nextArtists, previousArtists: previousArtists);
  }

  Future<void> _removeArtist(String artist) async {
    final previousArtists = List<String>.from(_artists.cast<String>());
    final nextArtists =
        previousArtists.where((item) => item != artist).toList();
    await _persistArtists(nextArtists, previousArtists: previousArtists);
  }

  Future<void> _persistArtists(
    List<String> nextArtists, {
    required List<String> previousArtists,
  }) async {
    final auth = context.read<AuthProvider>();
    setState(() {
      _artists = List<String>.from(nextArtists);
      _isSavingArtists = true;
    });

    try {
      await ApiService.updateArtists(nextArtists);
      final user = auth.user;
      if (user != null) {
        auth.refreshUser({
          ...user,
          'preferred_artists': List<String>.from(nextArtists),
        });
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _artists = List<String>.from(previousArtists);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not save preferred artists right now.'),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSavingArtists = false;
        });
      }
    }
  }

  Future<void> _updatePersonalizationOptIn(bool enabled) async {
    final success = await context
        .read<AuthProvider>()
        .updateProfile({'personalization_opt_in': enabled});
    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          success
              ? (enabled
                  ? 'Mood-based personalization is on.'
                  : 'Mood-based personalization is off.')
              : 'Could not update personalization right now.',
        ),
      ),
    );
  }

  void _showEditProfile(BuildContext ctx, Map<String, dynamic> user) {
    final usernameCtrl = TextEditingController(text: user['username']);
    showDialog(
      context: ctx,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.darkCard,
        title:
            const Text('Edit Profile', style: TextStyle(color: Colors.white)),
        content: TextField(
          controller: usernameCtrl,
          style: const TextStyle(color: Colors.white),
          decoration: const InputDecoration(labelText: 'Display name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              await context
                  .read<AuthProvider>()
                  .updateProfile({'username': usernameCtrl.text});
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  void _showChangePassword(BuildContext ctx) {
    final oldCtrl = TextEditingController();
    final newCtrl = TextEditingController();
    showDialog(
      context: ctx,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.darkCard,
        title: const Text('Change Password',
            style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: oldCtrl,
              obscureText: true,
              style: const TextStyle(color: Colors.white),
              decoration: const InputDecoration(labelText: 'Old Password'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: newCtrl,
              obscureText: true,
              style: const TextStyle(color: Colors.white),
              decoration: const InputDecoration(labelText: 'New Password'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () async {
              await ApiService.changePassword(oldCtrl.text, newCtrl.text);
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: const Text('Change'),
          ),
        ],
      ),
    );
  }
}

Widget _sectionTitle(String title, bool isDark) => Text(
      title,
      style: TextStyle(
        color: isDark ? Colors.white : Colors.black87,
        fontSize: 16,
        fontWeight: FontWeight.bold,
      ),
    );

Widget _card(bool isDark, {required Widget child}) => Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkCard : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: isDark ? AppColors.darkBorder : Colors.grey.shade200),
      ),
      child: child,
    );

Widget _divider(bool isDark) => Divider(
      color: isDark ? AppColors.darkBorder : Colors.grey.shade200,
      height: 1,
    );

Widget _settingsTile(
    IconData icon, String title, VoidCallback? onTap, bool isDark,
    {Widget? trailing}) {
  return ListTile(
    contentPadding: EdgeInsets.zero,
    leading: Icon(icon, color: AppColors.accent),
    title: Text(title,
        style: TextStyle(color: isDark ? Colors.white : Colors.black87)),
    trailing: trailing ?? const Icon(Icons.chevron_right, color: Colors.grey),
    onTap: onTap,
  );
}

/// The avatar/username/email/Spotify-connection-badge block at the top of
/// the profile screen, pulled out of `build()` since it's a large
/// self-contained, purely-display section.
class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.user, required this.isDark});

  final Map<String, dynamic> user;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final isSpotifyConnected = user['is_spotify_connected'] == true;
    return Center(
      child: Column(
        children: [
          CircleAvatar(
            radius: 50,
            backgroundColor: AppColors.accent.withValues(alpha: 0.2),
            child: Text(
              (user['username'] as String? ?? 'U')[0].toUpperCase(),
              style: const TextStyle(
                fontSize: 40,
                fontWeight: FontWeight.bold,
                color: AppColors.accent,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            user['username'] ?? '',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: isDark ? Colors.white : Colors.black87,
            ),
          ),
          Text(
            user['email'] ?? '',
            style: TextStyle(
              color: isDark ? Colors.white54 : Colors.black54,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: (isSpotifyConnected ? Colors.green : Colors.grey)
                  .withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isSpotifyConnected ? Colors.green : Colors.grey,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.music_note,
                    size: 14,
                    color: isSpotifyConnected ? Colors.green : Colors.grey),
                const SizedBox(width: 4),
                Text(
                  isSpotifyConnected
                      ? 'Spotify Connected'
                      : 'Spotify Not Connected',
                  style: TextStyle(
                    color: isSpotifyConnected ? Colors.green : Colors.grey,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
