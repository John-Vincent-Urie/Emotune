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

  /// Black or white, whichever reads better on [fill] (at least 4.85:1 on
  /// every mood color).
  static Color inkFor(Color fill) {
    final l = fill.computeLuminance();
    final onWhite = 1.05 / (l + 0.05);
    final onBlack = (l + 0.05) / 0.05;
    return onBlack >= onWhite ? Colors.black : Colors.white;
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    // On a filled chip the label sits on the mood color, so pick whichever
    // ink measures higher contrast against it. The brightness estimate this
    // replaced chose white on orange-red and dark on slate, both under 4.5:1.
    final onSelected = inkFor(color);

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
