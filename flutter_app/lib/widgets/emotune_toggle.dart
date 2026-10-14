import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// A small gradient-filled switch matching the HTML mockup's `.toggle`,
/// standing in for Material's [Switch] on the redesigned settings rows.
class EmoTuneToggle extends StatelessWidget {
  const EmoTuneToggle({
    super.key,
    required this.value,
    required this.onChanged,
    required this.label,
  });

  final bool value;
  final ValueChanged<bool> onChanged;
  // What the switch controls; without it TalkBack announced "switch, on" with
  // no hint of which setting.
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Semantics(
      toggled: value,
      label: label,
      child: GestureDetector(
        onTap: () => onChanged(!value),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
          width: 42,
          height: 24,
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            gradient: value
                ? const LinearGradient(
                    colors: [AppColors.teal, AppColors.lime],
                  )
                : null,
            color: value ? null : colors.divider.withValues(alpha: 0.9),
          ),
          child: AnimatedAlign(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
            alignment: value ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.25),
                    blurRadius: 3,
                    offset: const Offset(0, 1),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
