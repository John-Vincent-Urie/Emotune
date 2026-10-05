import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// The small pill used to filter by mood on the Discover grid -- a dot plus
/// a label, filled with the mood's color when selected. Matches the HTML
/// mockup's `.chip`.
class EmotionChip extends StatelessWidget {
  const EmotionChip({
    super.key,
    required this.label,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    // On a filled chip the label sits on the mood color, so pick the ink
    // that actually contrasts with it rather than assuming dark text.
    const onDark = Colors.white;
    const onLight = Color(0xFF14180F);
    final onSelected =
        ThemeData.estimateBrightnessForColor(color) == Brightness.dark
            ? onDark
            : onLight;

    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected ? color : colors.card,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selected ? color : colors.divider,
              width: 1.4,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: selected ? onSelected : color,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  color: selected ? onSelected : colors.textSecondary,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
