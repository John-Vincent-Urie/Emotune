import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

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
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkCard : Colors.white,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: isDark ? AppColors.darkBorder : Colors.black12,
        ),
        boxShadow: isDark
            ? null
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 18,
                  offset: const Offset(0, 10),
                ),
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  gradient: AppColors.buttonGradient,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.tune_rounded,
                  color: Colors.black,
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: isDark ? Colors.white : Colors.black87,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: TextStyle(
                        color: isDark ? Colors.white70 : Colors.black54,
                        fontSize: 12,
                        height: 1.45,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const _SectionLabel(
            label: 'Session Length',
            helper: 'Auto leaves the session untimed until you pick a length.',
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _sessionOptions.map((option) {
              final isSelected = option.value == sessionLengthMinutes;
              return ChoiceChip(
                label: Text(option.label),
                selected: isSelected,
                onSelected: (_) => onSessionLengthChanged(option.value),
                selectedColor: AppColors.gradientStart.withValues(alpha: 0.18),
                labelStyle: TextStyle(
                  color: isSelected
                      ? (isDark ? Colors.white : Colors.black87)
                      : (isDark ? Colors.white70 : Colors.black54),
                ),
                side: BorderSide(
                  color: isSelected
                      ? AppColors.gradientStart
                      : (isDark ? Colors.white12 : Colors.black12),
                ),
                backgroundColor: isDark
                    ? AppColors.darkCard
                    : Colors.grey.shade50,
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          const _SectionLabel(
            label: 'Taste Control',
            helper:
                'Balanced opens with the EmoTune list for that emotion, More '
                'familiar opens with the songs you hearted for it, and More '
                'discovery pulls fresh Spotify tracks instead of the built-in '
                'list.',
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _familiarityOptions.map((option) {
              final isSelected = option.value == familiarity;
              return ChoiceChip(
                label: Text(option.label),
                selected: isSelected,
                onSelected: (_) => onFamiliarityChanged(option.value),
                selectedColor: AppColors.gradientEnd.withValues(alpha: 0.18),
                labelStyle: TextStyle(
                  color: isSelected
                      ? (isDark ? Colors.white : Colors.black87)
                      : (isDark ? Colors.white70 : Colors.black54),
                ),
                side: BorderSide(
                  color: isSelected
                      ? AppColors.gradientEnd
                      : (isDark ? Colors.white12 : Colors.black12),
                ),
                backgroundColor: isDark
                    ? AppColors.darkCard
                    : Colors.grey.shade50,
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          _ToggleRow(
            title: 'Prefer instrumental',
            subtitle: 'Search for instrumental music first, then rank it above '
                'vocal-led tracks.',
            value: preferInstrumental,
            onChanged: onPreferInstrumentalChanged,
          ),
          const SizedBox(height: 10),
          _ToggleRow(
            title: 'Train on this session',
            subtitle: 'Turn this off when you want a private or experimental session.',
            value: trainOnThisSession,
            onChanged: onTrainOnThisSessionChanged,
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({
    required this.label,
    required this.helper,
  });

  final String label;
  final String helper;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: isDark ? Colors.white : Colors.black87,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          helper,
          style: TextStyle(
            color: isDark ? Colors.white60 : Colors.black45,
            fontSize: 11,
            height: 1.4,
          ),
        ),
      ],
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
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: isDark ? AppColors.darkCard : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isDark ? Colors.white10 : Colors.black12,
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: isDark ? Colors.white : Colors.black87,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: isDark ? Colors.white60 : Colors.black45,
                    fontSize: 11,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Switch.adaptive(
            value: value,
            activeThumbColor: AppColors.accent,
            onChanged: onChanged,
          ),
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
