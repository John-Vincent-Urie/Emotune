import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/support_contacts.dart';
import '../../theme/app_theme.dart';

/// Tap-to-dial rows for the contacts that have a phone number, compact enough
/// to sit inside the Home check-in banner. A link to a separate page asks a
/// struggling user for one more decision; the numbers belong where they are
/// already reading.
class SupportContactQuickList extends StatelessWidget {
  const SupportContactQuickList({super.key, required this.resources});

  final List<Map<String, dynamic>> resources;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final dialable = resources
        .where((r) => (r['phone']?.toString().trim() ?? '').isNotEmpty)
        .toList();

    return Column(
      children: [
        for (final resource in dialable)
          _ContactRow(resource: resource, colors: colors),
      ],
    );
  }
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({required this.resource, required this.colors});

  final Map<String, dynamic> resource;
  final EmoTuneColors colors;

  String _field(String key) => resource[key]?.toString().trim() ?? '';

  Future<void> _dial(BuildContext context, String phone) async {
    var opened = false;
    try {
      opened = await launchUrl(
        dialUri(phone),
        mode: LaunchMode.externalApplication,
      );
    } catch (_) {}
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open the dialer. The number is $phone.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = _field('name');
    final phone = _field('phone');
    final detail = [_field('hours'), _field('kind_label')]
        .where((part) => part.isNotEmpty)
        .join(' · ');

    return Semantics(
      button: true,
      label: 'Call $name, $phone',
      onTap: () => _dial(context, phone),
      excludeSemantics: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () => _dial(context, phone),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: TextStyle(
                        color: colors.textPrimary,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (detail.isNotEmpty)
                      Text(
                        detail,
                        style: TextStyle(
                          color: colors.textSecondary,
                          fontSize: 11.5,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: colors.safety,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.call, size: 15, color: colors.onSafety),
                    const SizedBox(width: 5),
                    Text(
                      phone,
                      style: TextStyle(
                        color: colors.onSafety,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
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
}
