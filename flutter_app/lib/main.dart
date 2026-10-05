import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'providers/recommendation_studio_provider.dart';
import 'providers/theme_provider.dart';
import 'providers/player_provider.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';
import 'screens/auth/splash_screen.dart';
import 'screens/auth/welcome_screen.dart';
import 'screens/auth/login_register_screen.dart';
import 'screens/home/main_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  unawaited(ApiService.warmUp());
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
  final _navigatorKey = GlobalKey<NavigatorState>();
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();

  @override
  void initState() {
    super.initState();
    // ApiService has already cleared the tokens by the time this runs; reset
    // the signed-in state and, if the user was inside the app, send them to
    // login instead of leaving every screen failing with 401s.
    ApiService.onSessionExpired = () async {
      if (!mounted || !context.read<AuthProvider>().handleSessionExpired()) {
        return;
      }
      _navigatorKey.currentState
          ?.pushNamedAndRemoveUntil('/login', (route) => false);
      _messengerKey.currentState?.showSnackBar(
        const SnackBar(
          content: Text('Your session expired. Please sign in again.'),
        ),
      );
    };
    // Load saved user session
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthProvider>().loadUser();
    });
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();

    // A theme swap repaints every token at once; crossfading it reads as the
    // app changing its mind rather than blinking. MediaQuery is available here
    // because View installs it above MaterialApp.
    final reduceMotion = MediaQuery.maybeOf(context)?.disableAnimations ?? false;

    return MaterialApp(
      navigatorKey: _navigatorKey,
      scaffoldMessengerKey: _messengerKey,
      title: 'EmoTune',
      debugShowCheckedModeBanner: false,
      theme: buildLightTheme(),
      darkTheme: buildDarkTheme(),
      themeMode: themeProvider.themeMode,
      themeAnimationDuration:
          reduceMotion ? Duration.zero : const Duration(milliseconds: 400),
      themeAnimationCurve: Curves.easeInOut,
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
