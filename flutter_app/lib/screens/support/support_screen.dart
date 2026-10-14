import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';
import '../../services/dialer.dart';
import '../../services/support_contacts.dart';
import '../../theme/app_theme.dart';

/// Full-screen support page shown when the backend's safety check fires.
///
/// [level] is `crisis` (explicit self-harm language: no music was returned) or
/// `concern` (hopeless language: music still plays, this is the "talk to
/// someone" follow-up). The resource list comes embedded in the analyze
/// response; if it is empty the page shows the contacts bundled in the app
/// straight away and swaps in the server's list if a fetch succeeds, so it
/// works offline and never renders without someone to call.
class SupportScreen extends StatefulWidget {
  const SupportScreen({
    super.key,
    required this.level,
    required this.message,
    this.resources = const [],
    this.about = 'self',
  });

  final String level;
  final String message;
  final List<dynamic> resources;
  // The backend's `support_about`: "someone_else" when the user is worried
  // about another person, so the page must not talk as if they were at risk.
  final String about;

  static Future<void> open(
    BuildContext context, {
    required String level,
    required String message,
    List<dynamic> resources = const [],
    String about = 'self',
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => SupportScreen(
          level: level,
          message: message,
          resources: resources,
          about: about,
        ),
      ),
    );
  }

  @override
  State<SupportScreen> createState() => _SupportScreenState();
}

class _SupportScreenState extends State<SupportScreen> {
  late List<Map<String, dynamic>> _resources =
      supportContactsOrBundled(widget.resources);

  bool get _isCrisis => widget.level == 'crisis';
  bool get _aboutSomeoneElse => widget.about == 'someone_else';

  String get _title {
    if (_aboutSomeoneElse) return "You're doing the right thing by asking";
    return _isCrisis ? "You don't have to go through this alone" : 'Checking in on you';
  }

  @override
  void initState() {
    super.initState();
    if (widget.resources.isEmpty) {
      _fetchResources();
    }
  }

  Future<void> _fetchResources() async {
    try {
      final result = await ApiService.getSupportResources();
      final fetched = List<dynamic>.from(result['resources'] ?? []);
      if (!mounted || fetched.isEmpty) return;
      setState(() => _resources = supportContactsOrBundled(fetched));
    } catch (_) {
      // Offline or failing: the bundled contacts are already on screen.
    }
  }

  Future<void> _dial(String phone) async {
    final opened = await openDialer(phone);
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open the dialer. The number is $phone.')),
      );
    }
  }

  Future<void> _launch(Uri uri) async {
    var opened = false;
    try {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {}
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open ${uri.scheme == 'tel' ? 'the dialer' : 'that app'}.')),
      );
    }
  }

  static String _digits(String value) => value.replaceAll(RegExp(r'[^0-9+]'), '');

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;

    return Scaffold(
      backgroundColor: colors.background,
      appBar: AppBar(
        backgroundColor: colors.background,
        elevation: 0,
        leading: IconButton(
          icon: Icon(Icons.close, color: colors.textPrimary),
          tooltip: 'Close',
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Icon(Icons.favorite, color: colors.safety, size: 32),
            const SizedBox(height: 12),
            Text(
              _title,
              style: TextStyle(
                color: colors.textPrimary,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              widget.message,
              style: TextStyle(color: colors.textPrimary, fontSize: 15, height: 1.5),
            ),
            const SizedBox(height: 24),
            Text(
              _isCrisis ? 'Reach out now' : 'People who can help',
              style: TextStyle(
                color: colors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.4,
              ),
            ),
            const SizedBox(height: 8),
            ..._resources.map((resource) => _resourceCard(colors, resource)),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: colors.textPrimary,
                side: BorderSide(color: colors.divider),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              icon: const Icon(Icons.chat_bubble_outline),
              label: const Text('Message someone I trust'),
              onPressed: () => _launch(Uri(scheme: 'sms')),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(
                _isCrisis ? 'Go back' : 'Back to my music',
                style: TextStyle(color: colors.textSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _resourceCard(EmoTuneColors colors, Map<String, dynamic> resource) {
    String field(String key) => resource[key]?.toString().trim() ?? '';
    final phone = field('phone');
    final sms = field('sms');
    final email = field('email');
    final website = field('website');
    final details = [
      field('kind_label'),
      field('hours'),
      field('languages'),
      if (resource['is_free'] == true) 'Free',
      field('location'),
    ].where((part) => part.isNotEmpty).join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: field('kind') == 'emergency' ? colors.safety : colors.divider,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            field('name'),
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          if (details.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(details, style: TextStyle(color: colors.textSecondary, fontSize: 12)),
          ],
          if (field('description').isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              field('description'),
              style: TextStyle(color: colors.textPrimary, fontSize: 13, height: 1.4),
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (phone.isNotEmpty)
                Semantics(
                  button: true,
                  label: 'Call ${field('name')}, $phone',
                  // Read the contact's name with the number, not just
                  // "Call 1553"; the tap moves here with the label.
                  onTap: () => _dial(phone),
                  excludeSemantics: true,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: colors.safety,
                      foregroundColor: colors.onSafety,
                    ),
                    icon: const Icon(Icons.call, size: 18),
                    label: Text('Call $phone'),
                    onPressed: () => _dial(phone),
                  ),
                ),
              if (sms.isNotEmpty)
                _secondaryButton(colors, Icons.sms_outlined, 'Text',
                    () => _launch(Uri(scheme: 'sms', path: _digits(sms)))),
              if (email.isNotEmpty)
                _secondaryButton(colors, Icons.mail_outline, 'Email',
                    () => _launch(Uri(scheme: 'mailto', path: email))),
              if (website.isNotEmpty)
                _secondaryButton(colors, Icons.open_in_new, 'Website',
                    () => _launch(Uri.parse(website))),
            ],
          ),
        ],
      ),
    );
  }

  Widget _secondaryButton(
    EmoTuneColors colors,
    IconData icon,
    String label,
    VoidCallback onPressed,
  ) {
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: colors.textPrimary,
        side: BorderSide(color: colors.divider),
      ),
      icon: Icon(icon, size: 18),
      label: Text(label),
      onPressed: onPressed,
    );
  }
}
