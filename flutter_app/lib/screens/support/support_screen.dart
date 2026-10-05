import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';

/// Full-screen support page shown when the backend's safety check fires.
///
/// [level] is `crisis` (explicit self-harm language: no music was returned) or
/// `concern` (hopeless language: music still plays, this is the "talk to
/// someone" follow-up). The resource list comes embedded in the analyze
/// response; if it is empty the page fetches it again, and if that fails too it
/// still shows the message, which always tells the user to contact local
/// emergency services. It must never render as a blank page.
class SupportScreen extends StatefulWidget {
  const SupportScreen({
    super.key,
    required this.level,
    required this.message,
    this.resources = const [],
  });

  final String level;
  final String message;
  final List<dynamic> resources;

  static Future<void> open(
    BuildContext context, {
    required String level,
    required String message,
    List<dynamic> resources = const [],
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => SupportScreen(
          level: level,
          message: message,
          resources: resources,
        ),
      ),
    );
  }

  @override
  State<SupportScreen> createState() => _SupportScreenState();
}

class _SupportScreenState extends State<SupportScreen> {
  static const Color _amber = Color(0xFFFFB020);

  late List<Map<String, dynamic>> _resources = _normalize(widget.resources);
  bool _loading = false;

  bool get _isCrisis => widget.level == 'crisis';

  @override
  void initState() {
    super.initState();
    if (_resources.isEmpty) {
      _fetchResources();
    }
  }

  static List<Map<String, dynamic>> _normalize(List<dynamic> raw) => raw
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();

  Future<void> _fetchResources() async {
    setState(() => _loading = true);
    try {
      final result = await ApiService.getSupportResources();
      if (!mounted) return;
      setState(() {
        _resources = _normalize(List<dynamic>.from(result['resources'] ?? []));
      });
    } catch (_) {
      // The message below still carries the emergency guidance.
    } finally {
      if (mounted) setState(() => _loading = false);
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
            const Icon(Icons.favorite, color: _amber, size: 32),
            const SizedBox(height: 12),
            Text(
              _isCrisis ? "You don't have to go through this alone" : 'Checking in on you',
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
              _isCrisis ? 'Reach out now' : 'People you can talk to',
              style: TextStyle(
                color: colors.textSecondary,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.4,
              ),
            ),
            const SizedBox(height: 8),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_resources.isEmpty)
              _infoCard(
                colors,
                'If you are in immediate danger, call your local emergency number. '
                'You can also talk to your school guidance counselor or someone you trust.',
              )
            else
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

  Widget _infoCard(EmoTuneColors colors, String text) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _amber.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _amber),
      ),
      child: Text(text, style: TextStyle(color: colors.textPrimary, height: 1.5)),
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
        border: Border.all(color: field('kind') == 'emergency' ? _amber : colors.divider),
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
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: _amber,
                    foregroundColor: Colors.black,
                  ),
                  icon: const Icon(Icons.call, size: 18),
                  label: Text('Call $phone'),
                  onPressed: () => _launch(Uri(scheme: 'tel', path: _digits(phone))),
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
