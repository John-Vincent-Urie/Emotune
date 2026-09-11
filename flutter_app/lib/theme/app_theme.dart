import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  // Brand gradient colors -- teal -> mint -> lime, the EmoTune identity used
  // on the welcome screen and now carried through the whole app.
  static const Color teal = Color(0xFF3EE7C4);
  static const Color mint = Color(0xFF8FE39A);
  static const Color lime = Color(0xFFCFF24A);

  // Kept as aliases so the ~90 existing call sites retint automatically.
  static const Color gradientStart = teal;
  static const Color gradientMid = mint;
  static const Color gradientEnd = lime;

  // Dark theme -- a near-black base rather than pure black, so cards and
  // glows have somewhere to sit.
  static const Color darkBg = Color(0xFF050608);
  static const Color darkSurface = Color(0xFF0D1210);
  static const Color darkCard = Color(0xFF141A17);
  static const Color darkBorder = Color(0xFF232B27);

  // Vignette used behind the animated backdrop on onboarding-style screens.
  static const Color vignetteInner = Color(0xFF0B0F0E);
  static const Color vignetteOuter = Color(0xFF030303);

  // Text roles, for the small set of surfaces that read from the palette
  // directly rather than through the theme's textTheme.
  static const Color textPrimary = Color(0xFFF3F6F3);
  static const Color textSecondary = Color(0xFF93A199);
  static const Color textFine = Color(0xFF5C6A61);

  // Light theme
  static const Color lightBg = Color(0xFFF5F5F5);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightCard = Color(0xFFEEEEEE);

  // Brand accent -- the lime step of the gradient reads well as a single
  // accent color against both the dark and light surfaces.
  static const Color accent = lime;
  static const Color accentDark = Color(0xFF3F9E6E);

  // Button gradient
  static const LinearGradient buttonGradient = LinearGradient(
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
    colors: [teal, mint, lime],
  );

  // Logo gradient
  static const LinearGradient logoGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [teal, mint, lime],
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

/// Display font for headlines and wordmarks -- the same Fraunces italic used
/// on the welcome screen, applied wherever a screen wants that brand voice.
TextStyle emoTuneHeadlineFont({
  double fontSize = 26,
  FontWeight fontWeight = FontWeight.w700,
  Color? color,
  double? height,
}) {
  return GoogleFonts.fraunces(
    fontSize: fontSize,
    fontWeight: fontWeight,
    color: color,
    height: height,
  );
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
    textTheme: GoogleFonts.manropeTextTheme(ThemeData.dark().textTheme).copyWith(
      displayLarge: GoogleFonts.fraunces(color: Colors.white, fontWeight: FontWeight.w600),
      displayMedium: GoogleFonts.fraunces(color: Colors.white, fontWeight: FontWeight.w600),
      headlineLarge: GoogleFonts.fraunces(color: Colors.white, fontWeight: FontWeight.w600),
      headlineMedium: GoogleFonts.fraunces(color: Colors.white, fontWeight: FontWeight.w600),
      headlineSmall: GoogleFonts.fraunces(color: Colors.white, fontWeight: FontWeight.w600),
      bodyLarge: GoogleFonts.manrope(color: Colors.white),
      bodyMedium: GoogleFonts.manrope(color: Colors.white70),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.darkBg,
      elevation: 0,
      iconTheme: const IconThemeData(color: Colors.white),
      titleTextStyle: GoogleFonts.fraunces(
        color: Colors.white,
        fontSize: 19,
        fontWeight: FontWeight.w600,
      ),
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
    textTheme: GoogleFonts.manropeTextTheme(ThemeData.light().textTheme).copyWith(
      displayLarge: GoogleFonts.fraunces(fontWeight: FontWeight.w600),
      displayMedium: GoogleFonts.fraunces(fontWeight: FontWeight.w600),
      headlineLarge: GoogleFonts.fraunces(fontWeight: FontWeight.w600),
      headlineMedium: GoogleFonts.fraunces(fontWeight: FontWeight.w600),
      headlineSmall: GoogleFonts.fraunces(fontWeight: FontWeight.w600),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.lightBg,
      elevation: 0,
      iconTheme: const IconThemeData(color: Colors.black87),
      titleTextStyle: GoogleFonts.fraunces(
        color: Colors.black87,
        fontSize: 19,
        fontWeight: FontWeight.w600,
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
