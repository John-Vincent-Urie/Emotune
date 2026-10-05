import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../../widgets/emotune_toggle.dart';

class RecommendationSessionControls extends StatelessWidget {
  const RecommendationSessionControls({
    super.key,
    required this.sessionLengthMinutes,
    required this.onSessionLengthChanged,
    required this.familiarity,
    required this.onFamiliarityChanged,
    required this.preferInstrumental,
    required this.onPreferInstrumentalChanged,
    required this.trainOnThisSession,
    required this.onTrainOnThisSessionChanged,
    this.title = 'Session Studio',
    this.subtitle =
        'Shape how long you want support, the taste of the playlist, and whether this session should teach personalization.',
  });

  final int? sessionLengthMinutes;
  final ValueChanged<int?> onSessionLengthChanged;
  final String familiarity;
  final ValueChanged<String> onFamiliarityChanged;
  final bool preferInstrumental;
  final ValueChanged<bool> onPreferInstrumentalChanged;
  final bool trainOnThisSession;
  final ValueChanged<bool> onTrainOnThisSessionChanged;
  final String title;
  final String subtitle;

  static const List<_NullableIntOption> _sessionOptions = [
    _NullableIntOption(value: null, label: 'Auto'),
    _NullableIntOption(value: 15, label: '15 min'),
    _NullableIntOption(value: 20, label: '20 min'),
    _NullableIntOption(value: 45, label: '45 min'),
  ];

  static const List<_StringOption> _familiarityOptions = [
    _StringOption(value: 'balanced', label: 'Balanced'),
    _StringOption(value: 'familiar', label: 'More familiar'),
    _StringOption(value: 'discovery', label: 'More discovery'),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: colors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    gradient: AppColors.buttonGradient,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.tune_rounded,
                    color: Color(0xFF08130D),
                    size: 16,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: colors.textPrimary,
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: colors.textSecondary,
                          fontSize: 11.5,
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const _FieldLabel(
            label: 'Session length',
            helper: 'Auto leaves the session untimed until you pick a length.',
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _sessionOptions.map((option) {
              return _SegButton(
                label: option.label,
                selected: option.value == sessionLengthMinutes,
                onTap: () => onSessionLengthChanged(option.value),
              );
            }).toList(),
          ),
          const SizedBox(height: 14),
          const _FieldLabel(
            label: 'Taste control',
            helper:
                'Balanced blends the EmoTune list, More familiar leans on songs '
                "you've hearted, More discovery pulls fresh tracks.",
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _familiarityOptions.map((option) {
              return _SegButton(
                label: option.label,
                selected: option.value == familiarity,
                onTap: () => onFamiliarityChanged(option.value),
              );
            }).toList(),
          ),
          const SizedBox(height: 6),
          _ToggleRow(
            title: 'Prefer instrumental',
            subtitle: 'Rank instrumental tracks above vocal-led ones.',
            value: preferInstrumental,
            onChanged: onPreferInstrumentalChanged,
          ),
          _ToggleRow(
            title: 'Train on this session',
            subtitle: 'Turn off for a private or experimental session.',
            value: trainOnThisSession,
            onChanged: onTrainOnThisSessionChanged,
          ),
        ],
      ),
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.label, required this.helper});

  final String label;
  final String helper;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: colors.textPrimary,
            fontSize: 12.5,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          helper,
          style: TextStyle(
            color: colors.textSecondary,
            fontSize: 11,
            height: 1.4,
          ),
        ),
      ],
    );
  }
}

/// The pill button used for session length / taste control -- a checkmark
/// prefixes the label when selected, matching the HTML mockup's `.seg-btn`.
class _SegButton extends StatelessWidget {
  const _SegButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
          decoration: BoxDecoration(
            color: colors.cardAlt,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: selected ? AppColors.mint : colors.divider,
              width: 1.4,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (selected) ...[
                const Icon(Icons.check_rounded, size: 12, color: AppColors.mint),
                const SizedBox(width: 5),
              ],
              Text(
                label,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: selected ? colors.textPrimary : colors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ToggleRow extends StatelessWidget {
  const _ToggleRow({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
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
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: colors.textSecondary,
                    fontSize: 11.5,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          EmoTuneToggle(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _NullableIntOption {
  const _NullableIntOption({
    required this.value,
    required this.label,
  });

  final int? value;
  final String label;
}

class _StringOption {
  const _StringOption({
    required this.value,
    required this.label,
  });

  final String value;
  final String label;
}
