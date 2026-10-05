import 'package:flutter/material.dart';

import '../../models/nav_destination.dart';
import '../../theme/app_theme.dart';
import '../favorites/favorites_screen.dart';
import '../history/history_screen.dart';
import '../home/home_screen.dart';
import '../profile/profile_screen.dart';
import '../recommendations/recommendations_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // Back button never signs the user out — it just returns to the Home
      // tab first, and only lets the app close once they're already there.
      canPop: _currentIndex == 0,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        setState(() => _currentIndex = 0);
      },
      child: Scaffold(
        body: IndexedStack(
          index: _currentIndex,
          children: [
            const HomeScreen(),
            FavoritesScreen(
              onExploreDiscover: () => setState(() => _currentIndex = 2),
            ),
            RecommendationsScreen(isActive: _currentIndex == 2),
            HistoryScreen(isActive: _currentIndex == 3),
            const ProfileScreen(),
          ],
        ),
        bottomNavigationBar: EmoTuneTabBar(
          currentIndex: _currentIndex,
          onSelected: (index) => setState(() => _currentIndex = index),
        ),
      ),
    );
  }
}

/// Five destinations built from [kNavItems], with a highlight pill that slides
/// between them rather than reappearing under the new tab.
class EmoTuneTabBar extends StatefulWidget {
  const EmoTuneTabBar({
    super.key,
    required this.currentIndex,
    required this.onSelected,
  });

  final int currentIndex;
  final ValueChanged<int> onSelected;

  @override
  State<EmoTuneTabBar> createState() => _EmoTuneTabBarState();
}

class _EmoTuneTabBarState extends State<EmoTuneTabBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _bounce;

  @override
  void initState() {
    super.initState();
    _bounce = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
  }

  @override
  void dispose() {
    _bounce.dispose();
    super.dispose();
  }

  bool get _reduceMotion => MediaQuery.of(context).disableAnimations;

  void _handleTap(int index) {
    if (!_reduceMotion) {
      _bounce.forward(from: 0);
    }
    widget.onSelected(index);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final isCompact = MediaQuery.sizeOf(context).width < 390;
    final horizontalPadding = isCompact ? 6.0 : 10.0;
    final reduceMotion = _reduceMotion;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.card,
        border: Border(top: BorderSide(color: colors.divider)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: horizontalPadding,
            vertical: 8,
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final slotWidth = constraints.maxWidth / kNavItems.length;

              return SizedBox(
                height: isCompact ? 54 : 58,
                child: Stack(
                  children: [
                    // The pill is positioned rather than decorating the active
                    // item, which is what lets it travel between slots.
                    AnimatedPositioned(
                      duration: reduceMotion
                          ? Duration.zero
                          : const Duration(milliseconds: 350),
                      curve: Curves.easeOutBack,
                      left: slotWidth * widget.currentIndex + 6,
                      top: 0,
                      bottom: 0,
                      width: slotWidth - 12,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: AppColors.mint.withValues(alpha: 0.14),
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                    ),
                    Row(
                      children: [
                        for (var i = 0; i < kNavItems.length; i++)
                          Expanded(
                            child: _TabButton(
                              item: kNavItems[i],
                              selected: widget.currentIndex == i,
                              colors: colors,
                              isCompact: isCompact,
                              bounce: _bounce,
                              reduceMotion: reduceMotion,
                              onTap: () => _handleTap(i),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.item,
    required this.selected,
    required this.colors,
    required this.isCompact,
    required this.bounce,
    required this.reduceMotion,
    required this.onTap,
  });

  final EmoTuneNavItem item;
  final bool selected;
  final EmoTuneColors colors;
  final bool isCompact;
  final Animation<double> bounce;
  final bool reduceMotion;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tint = selected ? AppColors.mint : colors.textSecondary;

    Widget icon = Icon(
      selected ? item.activeIcon : item.icon,
      color: tint,
      size: isCompact ? 22 : 24,
    );

    if (selected && !reduceMotion) {
      icon = AnimatedBuilder(
        animation: bounce,
        builder: (context, child) {
          final t = Curves.easeOut.transform(bounce.value);
          // Down and back up, so the tap reads as a press rather than a jump.
          final dip = (1 - t) * 4 * (1 - t);
          return Transform.translate(offset: Offset(0, dip), child: child);
        },
        child: icon,
      );
    }

    return Semantics(
      button: true,
      selected: selected,
      label: item.label,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            // The active icon sits a little proud of the rest.
            AnimatedSlide(
              duration:
                  reduceMotion ? Duration.zero : const Duration(milliseconds: 260),
              curve: Curves.easeOut,
              offset: selected ? const Offset(0, -0.12) : Offset.zero,
              child: icon,
            ),
            SizedBox(height: isCompact ? 3 : 4),
            Text(
              item.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: tint,
                fontSize: isCompact ? 9 : 10.5,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
