import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

class RecommendationSessionControls extends StatelessWidget {
  const RecommendationSessionControls({
    super.key,
    this.selectedOutcomeMode,
    this.onOutcomeModeChanged,
    required this.sessionLengthMinutes,
    required this.onSessionLengthChanged,
    required this.checkInFrequencyTracks,
    required this.onCheckInFrequencyChanged,
    required this.familiarity,
    required this.onFamiliarityChanged,
    required this.preferInstrumental,
    required this.onPreferInstrumentalChanged,
    required this.trainOnThisSession,
    required this.onTrainOnThisSessionChanged,
    this.title = 'Session Studio',
    this.subtitle =
        'Shape the playlist around the outcome you want, how long you want support, and whether this session should teach personalization.',
  });

  final String? selectedOutcomeMode;
  final ValueChanged<String>? onOutcomeModeChanged;
  final int? sessionLengthMinutes;
  final ValueChanged<int?> onSessionLengthChanged;
  final int? checkInFrequencyTracks;
  final ValueChanged<int?> onCheckInFrequencyChanged;
  final String familiarity;
  final ValueChanged<String> onFamiliarityChanged;
  final bool preferInstrumental;
  final ValueChanged<bool> onPreferInstrumentalChanged;
  final bool trainOnThisSession;
  final ValueChanged<bool> onTrainOnThisSessionChanged;
  final String title;
  final String subtitle;

  static const List<_ModeOption> _modeOptions = [
    _ModeOption(
      value: 'match_mood',
      label: 'Match My Mood',
      description: 'Stay close to the emotion EmoTune detected.',
    ),
    _ModeOption(
      value: 'calm_me_down',
      label: 'Calm Me Down',
      description: 'De-escalate intense feelings into something steadier.',
    ),
    _ModeOption(
      value: 'help_me_focus',
      label: 'Help Me Focus',
      description: 'Balance calm and momentum for concentration.',
    ),
    _ModeOption(
      value: 'lift_me_up',
      label: 'Lift Me Up',
      description: 'Nudge the energy upward without snapping the mood.',
    ),
    _ModeOption(
      value: 'sleep',
      label: 'Help Me Sleep',
      description: 'Bias toward soft, lower-stimulation tracks.',
    ),
  ];

  static const List<_NullableIntOption> _sessionOptions = [
    _NullableIntOption(value: null, label: 'Auto'),
    _NullableIntOption(value: 15, label: '15 min'),
    _NullableIntOption(value: 20, label: '20 min'),
    _NullableIntOption(value: 45, label: '45 min'),
  ];

  static const List<_NullableIntOption> _checkInOptions = [
    _NullableIntOption(value: null, label: 'Auto'),
    _NullableIntOption(value: 3, label: 'Every 3'),
    _NullableIntOption(value: 4, label: 'Every 4'),
    _NullableIntOption(value: 5, label: 'Every 5'),
  ];

  static const List<_StringOption> _familiarityOptions = [
    _StringOption(value: 'balanced', label: 'Balanced'),
    _StringOption(value: 'familiar', label: 'More familiar'),
    _StringOption(value: 'discovery', label: 'More discovery'),
  ];

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final onOutcomeModeChanged = this.onOutcomeModeChanged;
    final showOutcomeMode = onOutcomeModeChanged != null;
    final selectedMode = _modeOptions.firstWhere(
      (option) => option.value == selectedOutcomeMode,
      orElse: () => _modeOptions.first,
    );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF141414) : Colors.white,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: isDark ? const Color(0xFF2A2A2A) : Colors.black12,
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
          if (showOutcomeMode) ...[
            const SizedBox(height: 16),
            _SectionLabel(
              label: 'Outcome Mode',
              helper: selectedMode.description,
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _modeOptions.map((option) {
                final isSelected = option.value == selectedOutcomeMode;
                return ChoiceChip(
                  label: Text(option.label),
                  selected: isSelected,
                  onSelected: (_) => onOutcomeModeChanged(option.value),
                  selectedColor: AppColors.accent.withValues(alpha: 0.18),
                  labelStyle: TextStyle(
                    color: isSelected
                        ? (isDark ? AppColors.accent : Colors.black87)
                        : (isDark ? Colors.white70 : Colors.black54),
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  ),
                  side: BorderSide(
                    color: isSelected
                        ? AppColors.accent
                        : (isDark ? Colors.white12 : Colors.black12),
                  ),
                  backgroundColor: isDark
                      ? const Color(0xFF1B1B1B)
                      : Colors.grey.shade50,
                );
              }).toList(),
            ),
          ],
          const SizedBox(height: 16),
          const _SectionLabel(
            label: 'Session Length',
            helper: 'Auto uses the mode default. Match My Mood stays untimed until you pick a session length.',
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
                    ? const Color(0xFF1B1B1B)
                    : Colors.grey.shade50,
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          const _SectionLabel(
            label: 'Check-In Rhythm',
            helper: 'Auto follows the selected outcome mode.',
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _checkInOptions.map((option) {
              final isSelected = option.value == checkInFrequencyTracks;
              return ChoiceChip(
                label: Text(option.label),
                selected: isSelected,
                onSelected: (_) => onCheckInFrequencyChanged(option.value),
                selectedColor: AppColors.gradientMid.withValues(alpha: 0.18),
                labelStyle: TextStyle(
                  color: isSelected
                      ? (isDark ? Colors.white : Colors.black87)
                      : (isDark ? Colors.white70 : Colors.black54),
                ),
                side: BorderSide(
                  color: isSelected
                      ? AppColors.gradientMid
                      : (isDark ? Colors.white12 : Colors.black12),
                ),
                backgroundColor: isDark
                    ? const Color(0xFF1B1B1B)
                    : Colors.grey.shade50,
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          const _SectionLabel(
            label: 'Taste Control',
            helper: 'Bias recommendations toward comfort, discovery, or keep them balanced.',
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
                    ? const Color(0xFF1B1B1B)
                    : Colors.grey.shade50,
              );
            }).toList(),
          ),
          const SizedBox(height: 16),
          _ToggleRow(
            title: 'Prefer instrumental',
            subtitle: 'Push the ranking toward lower-lyric tracks when possible.',
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
        color: isDark ? const Color(0xFF1A1A1A) : Colors.grey.shade50,
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

class _ModeOption {
  const _ModeOption({
    required this.value,
    required this.label,
    required this.description,
  });

  final String value;
  final String label;
  final String description;
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
