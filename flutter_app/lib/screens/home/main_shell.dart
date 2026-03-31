import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../home/home_screen.dart';
import '../favorites/favorites_screen.dart';
import '../recommendations/recommendations_screen.dart';
import '../history/history_screen.dart';
import '../profile/profile_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final screenWidth = MediaQuery.sizeOf(context).width;
    final isCompactNav = screenWidth < 390;

    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: [
          const HomeScreen(),
          const FavoritesScreen(),
          RecommendationsScreen(isActive: _currentIndex == 2),
          const HistoryScreen(),
          const ProfileScreen(),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF111111) : Colors.white,
          border: Border(
            top: BorderSide(
              color: isDark ? const Color(0xFF2A2A2A) : Colors.grey.shade200,
            ),
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: isCompactNav ? 4 : 8,
              vertical: isCompactNav ? 4 : 6,
            ),
            child: Row(
              children: [
                _navItem(0, Icons.home_outlined, Icons.home, 'Home',
                    isCompact: isCompactNav),
                _navItem(1, Icons.favorite_outline, Icons.favorite, 'Favorites',
                    isCompact: isCompactNav),
                _navItem(
                    2, Icons.music_note_outlined, Icons.music_note, 'Discover',
                    isCompact: isCompactNav),
                _navItem(3, Icons.history, Icons.history, 'History',
                    isCompact: isCompactNav),
                _navItem(4, Icons.person_outline, Icons.person, 'Profile',
                    isCompact: isCompactNav),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _navItem(
    int index,
    IconData icon,
    IconData activeIcon,
    String label, {
    required bool isCompact,
  }) {
    final isActive = _currentIndex == index;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _currentIndex = index),
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          margin: EdgeInsets.symmetric(horizontal: isCompact ? 2 : 4),
          padding: EdgeInsets.symmetric(
            horizontal: isCompact ? 4 : 8,
            vertical: isCompact ? 5 : 6,
          ),
          decoration: BoxDecoration(
            color: isActive
                ? AppColors.accent.withOpacity(0.1)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                isActive ? activeIcon : icon,
                color: isActive
                    ? AppColors.accent
                    : (isDark ? Colors.white38 : Colors.black38),
                size: isCompact ? 22 : 24,
              ),
              SizedBox(height: isCompact ? 2 : 3),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: isActive
                      ? AppColors.accent
                      : (isDark ? Colors.white38 : Colors.black38),
                  fontSize: isCompact ? 9 : 10,
                  fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
