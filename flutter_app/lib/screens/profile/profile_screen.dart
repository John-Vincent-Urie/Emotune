import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../controllers/spotify_connection_controller.dart';
import '../../providers/auth_provider.dart';
import '../../providers/recommendation_studio_provider.dart';
import '../../providers/theme_provider.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotune_page_header.dart';
import '../../widgets/emotune_toggle.dart';
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
    final colors = context.emoColors;

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
      body: SafeArea(
        child: Column(
          children: [
            EmoTunePageHeader(
              title: 'Profile',
              actions: [
                EmoTuneIconButton(
                  icon: themeProvider.isDark
                      ? Icons.light_mode_outlined
                      : Icons.dark_mode_outlined,
                  onTap: themeProvider.toggleTheme,
                ),
                EmoTuneIconButton(
                  icon: Icons.logout_rounded,
                  onTap: () => _confirmLogout(context, auth),
                ),
              ],
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 2, 20, 32),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _ProfileHeader(user: user),

                    const _SectionTitle('Appearance'),
                    _SettingsCard(
                      children: [
                        _SettingsRow(
                          icon: Icons.dark_mode_outlined,
                          title: 'Dark mode',
                          trailing: EmoTuneToggle(
                            value: themeProvider.isDark,
                            onChanged: (_) => themeProvider.toggleTheme(),
                          ),
                        ),
                      ],
                    ),

                    const _SectionTitle('Preferred artists'),
                    _SettingsCard(
                      padding: const EdgeInsets.all(14),
                      children: [
                        Text(
                          "Artists we'll prioritize in recommendations.",
                          style: TextStyle(
                            color: colors.textSecondary,
                            fontSize: 11.5,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 10),
                        _SearchBox(
                          controller: _artistSearchCtrl,
                          enabled: !_isSavingArtists,
                          onChanged: _searchArtists,
                        ),
                        if (_searchResults.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Container(
                            decoration: BoxDecoration(
                              color: colors.cardAlt,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: colors.divider),
                            ),
                            child: Column(
                              children: _searchResults.take(5).map<Widget>((artist) {
                                final name = artist['name'] as String;
                                final saved = _artists.contains(name);
                                return ListTile(
                                  dense: true,
                                  leading: CircleAvatar(
                                    radius: 16,
                                    backgroundImage: artist['image'] != null
                                        ? NetworkImage(artist['image'])
                                        : null,
                                    backgroundColor:
                                        AppColors.accent.withValues(alpha: 0.2),
                                    child: artist['image'] == null
                                        ? Text(
                                            name.isNotEmpty ? name[0] : '?',
                                            style: const TextStyle(
                                                color: AppColors.accentDark),
                                          )
                                        : null,
                                  ),
                                  title: Text(
                                    name,
                                    style: TextStyle(color: colors.textPrimary),
                                  ),
                                  trailing: saved
                                      ? const Icon(Icons.check,
                                          color: AppColors.mint)
                                      : IconButton(
                                          icon: const Icon(Icons.add,
                                              color: AppColors.mint),
                                          onPressed: _isSavingArtists
                                              ? null
                                              : () => _addArtist(name),
                                        ),
                                );
                              }).toList(),
                            ),
                          ),
                        ],
                        if (_artists.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: _artists.map<Widget>((a) {
                              return _ArtistChip(
                                label: a.toString(),
                                onRemove: _isSavingArtists
                                    ? null
                                    : () => _removeArtist(a.toString()),
                              );
                            }).toList(),
                          ),
                        ],
                      ],
                    ),

                    const _SectionTitle('Privacy & personalization'),
                    _SettingsCard(
                      children: [
                        _SettingsRow(
                          icon: Icons.auto_awesome_rounded,
                          title: 'Mood-based personalization',
                          subtitle:
                              'Lets EmoTune learn from your sessions to improve future picks.',
                          trailing: EmoTuneToggle(
                            value: user['personalization_opt_in'] != false,
                            onChanged: _updatePersonalizationOptIn,
                          ),
                        ),
                      ],
                    ),

                    const _SectionTitle('Recommendation studio'),
                    RecommendationSessionControls(
                      sessionLengthMinutes: studio.sessionLengthMinutes,
                      onSessionLengthChanged: studio.setSessionLengthMinutes,
                      familiarity: studio.familiarity,
                      onFamiliarityChanged: studio.setFamiliarity,
                      preferInstrumental: studio.preferInstrumental,
                      onPreferInstrumentalChanged: studio.setPreferInstrumental,
                      trainOnThisSession: studio.trainOnThisSession,
                      onTrainOnThisSessionChanged: studio.setTrainOnThisSession,
                      title: 'Shape session timing and taste',
                      subtitle: 'Applies across Home and Discover.',
                    ),

                    const _SectionTitle('Account'),
                    _SettingsCard(
                      children: [
                        _SettingsRow(
                          icon: Icons.person_outline_rounded,
                          title: 'Edit profile',
                          chevron: true,
                          onTap: () => _showEditProfile(context, user),
                        ),
                        _SettingsRow(
                          icon: Icons.lock_outline_rounded,
                          title: 'Change password',
                          chevron: true,
                          onTap: () => _showChangePassword(context),
                        ),
                        _SettingsRow(
                          icon: Icons.graphic_eq_rounded,
                          title: _spotifyConnection.isConnecting
                              ? 'Connecting Spotify...'
                              : 'Connect Spotify',
                          subtitle: user['is_spotify_connected'] == true
                              ? 'Connected'
                              : null,
                          onTap: _spotifyConnection.isConnecting
                              ? null
                              : () => _spotifyConnection.connect(context),
                          trailing: _spotifyConnection.isConnecting
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2),
                                )
                              : user['is_spotify_connected'] == true
                                  ? const Icon(Icons.check_circle_rounded,
                                      color: AppColors.mint, size: 18)
                                  : null,
                        ),
                        if (user['is_spotify_connected'] == true)
                          _SettingsRow(
                            icon: Icons.link_off_rounded,
                            title: _spotifyConnection.isDisconnecting
                                ? 'Disconnecting Spotify...'
                                : 'Disconnect Spotify',
                            onTap: _spotifyConnection.isDisconnecting
                                ? null
                                : () => _spotifyConnection.disconnect(context),
                            trailing: _spotifyConnection.isDisconnecting
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2),
                                  )
                                : null,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
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

  Future<void> _confirmLogout(BuildContext ctx, AuthProvider auth) async {
    final colors = ctx.emoColors;
    final confirmed = await showDialog<bool>(
      context: ctx,
      builder: (dialogCtx) => AlertDialog(
        backgroundColor: colors.card,
        title: Text('Log out?', style: TextStyle(color: colors.textPrimary)),
        content: Text(
          'You will need to sign in again to access your account.',
          style: TextStyle(color: colors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Log out'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    await auth.logout();
    if (!ctx.mounted) return;
    Navigator.pushNamedAndRemoveUntil(ctx, '/welcome', (route) => false);
  }

  void _showEditProfile(BuildContext ctx, Map<String, dynamic> user) {
    final usernameCtrl = TextEditingController(text: user['username']);
    final colors = ctx.emoColors;
    showDialog(
      context: ctx,
      builder: (_) => AlertDialog(
        backgroundColor: colors.card,
        title: Text('Edit Profile', style: TextStyle(color: colors.textPrimary)),
        content: TextField(
          controller: usernameCtrl,
          style: TextStyle(color: colors.textPrimary),
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
    final colors = ctx.emoColors;
    showDialog(
      context: ctx,
      builder: (_) => AlertDialog(
        backgroundColor: colors.card,
        title: Text('Change Password', style: TextStyle(color: colors.textPrimary)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: oldCtrl,
              obscureText: true,
              style: TextStyle(color: colors.textPrimary),
              decoration: const InputDecoration(labelText: 'Old Password'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: newCtrl,
              obscureText: true,
              style: TextStyle(color: colors.textPrimary),
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

/// Small-caps section label above each settings card, matching the HTML
/// mockup's `.section-title`.
class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Padding(
      padding: const EdgeInsets.only(top: 20, bottom: 10),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          color: colors.textSecondary,
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

/// The rounded, bordered card that groups settings rows, matching the HTML
/// mockup's `.settings-card`.
class _SettingsCard extends StatelessWidget {
  const _SettingsCard({
    required this.children,
    this.padding,
  });

  final List<Widget> children;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Container(
      width: double.infinity,
      padding: padding ?? const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.divider),
      ),
      child: padding != null
          ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: children)
          : Column(
              children: [
                for (var i = 0; i < children.length; i++)
                  Container(
                    decoration: BoxDecoration(
                      border: i < children.length - 1
                          ? Border(bottom: BorderSide(color: colors.divider))
                          : null,
                    ),
                    child: children[i],
                  ),
              ],
            ),
    );
  }
}

/// One row inside a [_SettingsCard]: a tinted icon square, title/subtitle,
/// and either a trailing widget (toggle, status) or a chevron for navigation.
class _SettingsRow extends StatelessWidget {
  const _SettingsRow({
    required this.icon,
    required this.title,
    this.subtitle,
    this.trailing,
    this.chevron = false,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final bool chevron;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final row = Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(
              color: colors.cardAlt,
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(icon, size: 15, color: AppColors.mint),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: colors.textPrimary,
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: TextStyle(
                      color: colors.textSecondary,
                      fontSize: 11.5,
                      height: 1.4,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (trailing != null) trailing!,
          if (chevron && trailing == null)
            Icon(Icons.chevron_right_rounded, size: 18, color: colors.textSecondary),
        ],
      ),
    );

    if (onTap == null) {
      return row;
    }
    return InkWell(onTap: onTap, child: row);
  }
}

class _SearchBox extends StatelessWidget {
  const _SearchBox({
    required this.controller,
    required this.enabled,
    required this.onChanged,
  });

  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Container(
      decoration: BoxDecoration(
        color: colors.inputBackground,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          Icon(Icons.search_rounded, size: 16, color: colors.textSecondary),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              style: TextStyle(color: colors.textPrimary, fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Search an artist...',
                hintStyle: TextStyle(color: colors.textSecondary),
                border: InputBorder.none,
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(vertical: 12),
              ),
              onChanged: onChanged,
            ),
          ),
        ],
      ),
    );
  }
}

class _ArtistChip extends StatelessWidget {
  const _ArtistChip({required this.label, this.onRemove});

  final String label;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Container(
      padding: const EdgeInsets.only(left: 12, right: 6, top: 6, bottom: 6),
      decoration: BoxDecoration(
        color: colors.cardAlt,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: colors.divider),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 4),
          GestureDetector(
            onTap: onRemove,
            child: Icon(Icons.close_rounded, size: 15, color: colors.textSecondary),
          ),
        ],
      ),
    );
  }
}

/// The avatar/username/email/Spotify-connection-badge block at the top of
/// the profile screen, styled after the HTML mockup's `.avatar-block`.
class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.user});

  final Map<String, dynamic> user;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final isSpotifyConnected = user['is_spotify_connected'] == true;
    final initial = (user['username'] as String? ?? 'U')[0].toUpperCase();

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          children: [
            Container(
              width: 76,
              height: 76,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0x40CFF24A),
                    Color(0x333EE7C4),
                  ],
                ),
              ),
              alignment: Alignment.center,
              child: Text(
                initial,
                style: emoTuneHeadlineFont(fontSize: 28, color: AppColors.lime),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              user['username'] ?? '',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: colors.textPrimary,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              user['email'] ?? '',
              style: TextStyle(color: colors.textSecondary, fontSize: 12.5),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: isSpotifyConnected
                      ? AppColors.teal
                      : colors.divider,
                  width: 1.4,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.graphic_eq_rounded,
                    size: 13,
                    color: isSpotifyConnected
                        ? const Color(0xFF22B892)
                        : colors.textSecondary,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    isSpotifyConnected
                        ? 'Spotify connected'
                        : 'Spotify not connected',
                    style: TextStyle(
                      color: isSpotifyConnected
                          ? const Color(0xFF22B892)
                          : colors.textSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
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
}
