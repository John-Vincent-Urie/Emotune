import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// The `Title` + optional trailing icon row used at the top of every tab
/// except Home, replacing a Material [AppBar] so these screens read as part
/// of the same design system as the brand header on Home.
class EmoTunePageHeader extends StatelessWidget {
  const EmoTunePageHeader({
    super.key,
    required this.title,
    this.titleIcon,
    this.actions = const [],
  });

  final String title;
  final Widget? titleIcon;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Flexible(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Text(
                    title,
                    overflow: TextOverflow.ellipsis,
                    style: emoTuneHeadlineFont(
                      fontSize: 23,
                      color: colors.textPrimary,
                    ),
                  ),
                ),
                if (titleIcon != null) ...[
                  const SizedBox(width: 8),
                  titleIcon!,
                ],
              ],
            ),
          ),
          if (actions.isNotEmpty)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var i = 0; i < actions.length; i++) ...[
                  if (i > 0) const SizedBox(width: 8),
                  actions[i],
                ],
              ],
            ),
        ],
      ),
    );
  }
}

/// A circular bordered icon button matching the HTML mockup's `.icon-btn` --
/// used in page header actions (theme toggle, edit, etc).
class EmoTuneIconButton extends StatelessWidget {
  const EmoTuneIconButton({
    super.key,
    required this.icon,
    required this.label,
    this.onTap,
  });

  final IconData icon;
  // An icon alone reads as just "button" to a screen reader.
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: colors.card,
            border: Border.all(color: colors.divider),
          ),
          child: Icon(icon, size: 16, color: colors.textPrimary),
        ),
      ),
    );
  }
}
