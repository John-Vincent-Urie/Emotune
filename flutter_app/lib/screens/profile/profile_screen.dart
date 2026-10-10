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
  final _spotifyConnection = SpotifyConnectionController();

  @override
  void initState() {
    super.initState();
    _spotifyConnection.addListener(_onSpotifyConnectionChanged);
  }

  @override
  void dispose() {
    _spotifyConnection.removeListener(_onSpotifyConnectionChanged);
    _spotifyConnection.dispose();
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
                  label: themeProvider.isDark
                      ? 'Switch to light theme'
                      : 'Switch to dark theme',
                  onTap: themeProvider.toggleTheme,
                ),
                EmoTuneIconButton(
                  icon: Icons.logout_rounded,
                  label: 'Log out',
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
                            label: 'Dark mode',
                            value: themeProvider.isDark,
                            onChanged: (_) => themeProvider.toggleTheme(),
                          ),
                        ),
                      ],
                    ),

                    const _SectionTitle('Recommendation studio'),
                    RecommendationSessionControls(
                      sessionLengthMinutes: studio.sessionLengthMinutes,
                      onSessionLengthChanged: studio.setSessionLengthMinutes,
                      title: 'Shape session timing',
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
                                  ? Icon(Icons.check_circle_rounded,
                                      color: colors.accentText, size: 18)
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
    final confirmCtrl = TextEditingController();
    final colors = ctx.emoColors;
    String? error;
    var saving = false;
    var obscure = true;

    InputDecoration field(String label, {String? helper}) => InputDecoration(
          labelText: label,
          helperText: helper,
          // Wraps instead of cutting off at 360px wide.
          helperMaxLines: 2,
        );

    showDialog(
      context: ctx,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) {
          final toggle = IconButton(
            icon: Icon(obscure ? Icons.visibility_off : Icons.visibility),
            tooltip: obscure ? 'Show passwords' : 'Hide passwords',
            onPressed: () => setDialogState(() => obscure = !obscure),
          );
          return AlertDialog(
            backgroundColor: colors.card,
            // Without this the dialog was announced only as "Alert".
            semanticLabel: 'Change password',
            title: Text('Change Password', style: TextStyle(color: colors.textPrimary)),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    controller: oldCtrl,
                    obscureText: obscure,
                    style: TextStyle(color: colors.textPrimary),
                    decoration: field('Current password').copyWith(
                      suffixIcon: toggle,
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: newCtrl,
                    obscureText: obscure,
                    style: TextStyle(color: colors.textPrimary),
                    decoration: field(
                      'New password',
                      helper: 'At least 8 characters, not only numbers',
                    ),
                  ),
                  const SizedBox(height: 12),
                  // A typo in a hidden new password used to go unnoticed
                  // until the next login failed.
                  TextField(
                    controller: confirmCtrl,
                    obscureText: obscure,
                    style: TextStyle(color: colors.textPrimary),
                    decoration: field('Confirm new password'),
                  ),
                  // A rejected password used to fail silently: the dialog just
                  // stayed open. The server's reasons now show here.
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        error!,
                        style: TextStyle(
                          // 5.3:1 on the light card, 6.7:1 on the dark one.
                          color: Theme.of(dialogContext).brightness ==
                                  Brightness.light
                              ? const Color(0xFFC9302C)
                              : const Color(0xFFFF6B6B),
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(dialogContext),
                  child: const Text('Cancel')),
              ElevatedButton(
                onPressed: saving
                    ? null
                    : () async {
                        if (newCtrl.text != confirmCtrl.text) {
                          setDialogState(
                              () => error = 'New passwords do not match.');
                          return;
                        }
                        setDialogState(() {
                          saving = true;
                          error = null;
                        });
                        try {
                          await ApiService.changePassword(
                              oldCtrl.text, newCtrl.text);
                          if (!dialogContext.mounted) return;
                          Navigator.pop(dialogContext);
                          ScaffoldMessenger.of(ctx).showSnackBar(
                            const SnackBar(content: Text('Password changed.')),
                          );
                        } on ApiException catch (e) {
                          if (!dialogContext.mounted) return;
                          setDialogState(() {
                            saving = false;
                            // The server's "Wrong password" doesn't say which
                            // of the fields is wrong.
                            error = e.message == 'Wrong password'
                                ? 'Your current password is incorrect.'
                                : e.message;
                          });
                        }
                      },
                child: const Text('Change'),
              ),
            ],
          );
        },
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
  const _SettingsCard({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.divider),
      ),
      child: Column(
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
            child: Icon(icon, size: 15, color: colors.accentText),
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
                style: emoTuneHeadlineFont(
                  fontSize: 28,
                  color: context.emoColors.accentText,
                ),
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
                      ? colors.accentText
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
