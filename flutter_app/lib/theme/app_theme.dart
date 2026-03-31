import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  // Brand gradient colors (from logo)
  static const Color gradientStart = Color(0xFF7EFFD4);  // Mint
  static const Color gradientMid = Color(0xFF89F7C0);   // Green
  static const Color gradientEnd = Color(0xFFDDFF7E);   // Lime yellow

  // Dark theme
  static const Color darkBg = Color(0xFF000000);
  static const Color darkSurface = Color(0xFF111111);
  static const Color darkCard = Color(0xFF1A1A1A);
  static const Color darkBorder = Color(0xFF2A2A2A);

  // Light theme
  static const Color lightBg = Color(0xFFF5F5F5);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightCard = Color(0xFFEEEEEE);

  // Brand accent
  static const Color accent = Color(0xFF9EFF65);         // Lime green
  static const Color accentDark = Color(0xFF6BCF45);
  
  // Button gradient
  static const LinearGradient buttonGradient = LinearGradient(
    colors: [Color(0xFF9EFF65), Color(0xFFB8FF80)],
  );
  
  // Logo gradient
  static const LinearGradient logoGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF7EFFD4), Color(0xFF89E0FF), Color(0xFFDDFF7E)],
  );

  // Emotion colors
  static const Map<String, Color> emotionColors = {
    'happy': Color(0xFFFFD700),
    'sad': Color(0xFF4169E1),
    'angry': Color(0xFFFF4500),
    'motivational': Color(0xFFFF8C00),
    'fear': Color(0xFF800080),
    'depressing': Color(0xFF708090),
    'surprising': Color(0xFFFF69B4),
    'stressed': Color(0xFFDC143C),
    'calm': Color(0xFF3CB371),
    'lonely': Color(0xFF778899),
    'romantic': Color(0xFFFF1493),
    'nostalgic': Color(0xFFDEB887),
    'mixed': Color(0xFF9370DB),
  };
}

ThemeData buildDarkTheme() {
  return ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.darkBg,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.accent,
      secondary: AppColors.gradientStart,
      surface: AppColors.darkSurface,
    ),
    cardColor: AppColors.darkCard,
    textTheme: GoogleFonts.poppinsTextTheme(ThemeData.dark().textTheme).copyWith(
      displayLarge: GoogleFonts.poppins(color: Colors.white, fontWeight: FontWeight.bold),
      bodyLarge: GoogleFonts.poppins(color: Colors.white),
      bodyMedium: GoogleFonts.poppins(color: Colors.white70),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.darkBg,
      elevation: 0,
      iconTheme: IconThemeData(color: Colors.white),
      titleTextStyle: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.darkSurface,
      selectedItemColor: AppColors.accent,
      unselectedItemColor: Colors.white38,
      type: BottomNavigationBarType.fixed,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.darkSurface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.darkBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.darkBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.accent),
      ),
      hintStyle: const TextStyle(color: Colors.white38),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.accent,
        foregroundColor: Colors.black,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
        textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
      ),
    ),
  );
}

ThemeData buildLightTheme() {
  return ThemeData(
    brightness: Brightness.light,
    scaffoldBackgroundColor: AppColors.lightBg,
    colorScheme: const ColorScheme.light(
      primary: AppColors.accentDark,
      secondary: Color(0xFF00B894),
      surface: AppColors.lightSurface,
    ),
    cardColor: AppColors.lightSurface,
    textTheme: GoogleFonts.poppinsTextTheme(ThemeData.light().textTheme),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.lightBg,
      elevation: 0,
      iconTheme: const IconThemeData(color: Colors.black87),
      titleTextStyle: GoogleFonts.poppins(
        color: Colors.black87, fontSize: 18, fontWeight: FontWeight.w600,
      ),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.lightSurface,
      selectedItemColor: AppColors.accentDark,
      unselectedItemColor: Colors.black38,
      type: BottomNavigationBarType.fixed,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.lightSurface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Colors.black12),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Colors.black12),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.accentDark),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.accentDark,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
        textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
      ),
    ),
  );
}
