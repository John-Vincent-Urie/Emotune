import 'package:flutter/material.dart';

/// One bottom-tab destination. The shell builds its bar from this list, so the
/// order and count live in one place instead of five repeated call sites.
@immutable
class EmoTuneNavItem {
  const EmoTuneNavItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
  });

  final IconData icon;
  final IconData activeIcon;
  final String label;
}

const List<EmoTuneNavItem> kNavItems = [
  EmoTuneNavItem(
    icon: Icons.home_outlined,
    activeIcon: Icons.home_rounded,
    label: 'Home',
  ),
  EmoTuneNavItem(
    icon: Icons.favorite_outline,
    activeIcon: Icons.favorite_rounded,
    label: 'Favorites',
  ),
  EmoTuneNavItem(
    icon: Icons.explore_outlined,
    activeIcon: Icons.explore_rounded,
    label: 'Discover',
  ),
  EmoTuneNavItem(
    icon: Icons.history_outlined,
    activeIcon: Icons.history_rounded,
    label: 'History',
  ),
  EmoTuneNavItem(
    icon: Icons.person_outline,
    activeIcon: Icons.person_rounded,
    label: 'Profile',
  ),
];
