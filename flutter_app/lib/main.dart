import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'providers/recommendation_studio_provider.dart';
import 'providers/theme_provider.dart';
import 'providers/player_provider.dart';
import 'theme/app_theme.dart';
import 'screens/auth/splash_screen.dart';
import 'screens/auth/welcome_screen.dart';
import 'screens/auth/login_register_screen.dart';
import 'screens/home/main_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final recommendationStudioProvider = RecommendationStudioProvider();
  await recommendationStudioProvider.load();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => PlayerProvider()),
        ChangeNotifierProvider<RecommendationStudioProvider>.value(
          value: recommendationStudioProvider,
        ),
      ],
      child: const EmoTuneApp(),
    ),
  );
}

class EmoTuneApp extends StatefulWidget {
  const EmoTuneApp({super.key});

  @override
  State<EmoTuneApp> createState() => _EmoTuneAppState();
}

class _EmoTuneAppState extends State<EmoTuneApp> {
  @override
  void initState() {
    super.initState();
    // Load saved user session
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthProvider>().loadUser();
    });
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();

    return MaterialApp(
      title: 'EmoTune',
      debugShowCheckedModeBanner: false,
      theme: buildLightTheme(),
      darkTheme: buildDarkTheme(),
      themeMode: themeProvider.themeMode,
      initialRoute: '/',
      routes: {
        '/': (_) => const SplashScreen(),
        '/welcome': (_) => const WelcomeScreen(),
        '/login': (_) => const LoginScreen(),
        '/register': (_) => const RegisterScreen(),
        '/home': (_) => const MainShell(),
      },
      builder: (context, child) {
        return child!;
      },
    );
  }
}
