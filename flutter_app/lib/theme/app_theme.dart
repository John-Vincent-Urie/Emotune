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
  // Was #5C6A61, 3.6:1 on the dark backdrop -- under AA for 12px text.
  static const Color textFine = Color(0xFF7D8B82);

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

/// Every surface colour the redesigned screens use, in one object per theme.
///
/// Screens read these instead of branching on `isDark` with literal hex, which
/// is what lets a single theme swap repaint the whole app -- and, because
/// [lerp] interpolates every token, lets MaterialApp animate that swap instead
/// of snapping.
@immutable
class EmoTuneColors extends ThemeExtension<EmoTuneColors> {
  const EmoTuneColors({
    required this.background,
    required this.inputBackground,
    required this.card,
    required this.cardAlt,
    required this.textPrimary,
    required this.textSecondary,
    required this.divider,
    required this.safety,
    required this.onSafety,
    required this.accentText,
  });

  final Color background;
  final Color inputBackground;
  final Color card;
  // Matches the HTML design's `--card-bg-2` -- a step further from the page
  // background than [card], used for icon squares, reply bubbles and
  // unselected segmented buttons that sit on top of a card.
  final Color cardAlt;
  final Color textPrimary;
  final Color textSecondary;
  final Color divider;
  // Text, icons and borders on safety surfaces (check-in banner, support
  // screen). The brand amber #FFB020 is 1.6:1 on the light theme's amber
  // tint, so light uses a dark amber (5.5:1 there); dark keeps the bright one.
  final Color safety;
  // Foreground on a filled [safety] button.
  final Color onSafety;
  // The brand green for icons, ticks, spinners and text drawn straight on a
  // themed surface. Lime and mint are 1.2-1.4:1 on the light theme, so light
  // uses a deep green (5:1+); dark keeps mint.
  final Color accentText;

  static const EmoTuneColors light = EmoTuneColors(
    background: Color(0xFFF5F6F2),
    inputBackground: Color(0xFFEEEFEA),
    card: Color(0xFFFFFFFF),
    cardAlt: Color(0xFFF7F8F5),
    textPrimary: Color(0xFF1B1F1C),
    // #767F76 was 3.6-4.1:1 on every light surface, under AA for body text.
    textSecondary: Color(0xFF5F675F),
    divider: Color(0x14000000),
    safety: Color(0xFF8A5300),
    onSafety: Color(0xFFFFFFFF),
    accentText: Color(0xFF2B7838),
  );

  static const EmoTuneColors dark = EmoTuneColors(
    background: Color(0xFF06070A),
    inputBackground: Color(0xFF0E1210),
    card: Color(0xFF101413),
    cardAlt: Color(0xFF0D110F),
    textPrimary: Color(0xFFF3F6F3),
    textSecondary: Color(0xFF8B948C),
    divider: Color(0x14FFFFFF),
    safety: Color(0xFFFFB020),
    onSafety: Color(0xFF000000),
    accentText: AppColors.mint,
  );

  /// Convenience accessor so screens read `context.emoColors` rather than
  /// repeating the extension lookup.
  static EmoTuneColors of(BuildContext context) =>
      Theme.of(context).extension<EmoTuneColors>() ?? dark;

  @override
  EmoTuneColors copyWith({
    Color? background,
    Color? inputBackground,
    Color? card,
    Color? cardAlt,
    Color? textPrimary,
    Color? textSecondary,
    Color? divider,
    Color? safety,
    Color? onSafety,
    Color? accentText,
  }) {
    return EmoTuneColors(
      background: background ?? this.background,
      inputBackground: inputBackground ?? this.inputBackground,
      card: card ?? this.card,
      cardAlt: cardAlt ?? this.cardAlt,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      divider: divider ?? this.divider,
      safety: safety ?? this.safety,
      onSafety: onSafety ?? this.onSafety,
      accentText: accentText ?? this.accentText,
    );
  }

  @override
  EmoTuneColors lerp(ThemeExtension<EmoTuneColors>? other, double t) {
    if (other is! EmoTuneColors) {
      return this;
    }
    return EmoTuneColors(
      background: Color.lerp(background, other.background, t)!,
      inputBackground: Color.lerp(inputBackground, other.inputBackground, t)!,
      card: Color.lerp(card, other.card, t)!,
      cardAlt: Color.lerp(cardAlt, other.cardAlt, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      divider: Color.lerp(divider, other.divider, t)!,
      safety: Color.lerp(safety, other.safety, t)!,
      onSafety: Color.lerp(onSafety, other.onSafety, t)!,
      accentText: Color.lerp(accentText, other.accentText, t)!,
    );
  }
}

extension EmoTuneColorsContext on BuildContext {
  EmoTuneColors get emoColors => EmoTuneColors.of(this);
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
    scaffoldBackgroundColor: EmoTuneColors.dark.background,
    extensions: const [EmoTuneColors.dark],
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
    scaffoldBackgroundColor: EmoTuneColors.light.background,
    extensions: const [EmoTuneColors.light],
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
