import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../theme/app_theme.dart';
import '../../widgets/emotune_backdrop.dart';
import '../../widgets/emotune_buttons.dart';
import '../../widgets/emotune_logo.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnim;
  late Animation<double> _scaleAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );
    _fadeAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _controller, curve: const Interval(0, 0.6)),
    );
    _scaleAnim = Tween<double>(begin: 0.7, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.elasticOut),
    );
    _controller.forward();

    // Hold the splash for its usual three seconds, but route on the restored
    // session: going straight to Welcome logged every returning user out on
    // each launch or page reload even though their tokens were still valid.
    Future.delayed(const Duration(seconds: 3), _continue);
  }

  bool _routed = false;

  Future<void> _continue() async {
    if (_routed) return;
    _routed = true;
    final auth = context.read<AuthProvider>();
    await auth.loadUser();
    if (!mounted) return;
    Navigator.pushReplacementNamed(
      context,
      auth.isLoggedIn || auth.hasSavedSession ? '/home' : '/welcome',
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBg,
      body: Stack(
        children: [
          const Positioned.fill(child: EmoTuneBackdrop(showParticles: false)),
          Center(
            child: FadeTransition(
              opacity: _fadeAnim,
              child: ScaleTransition(
                scale: _scaleAnim,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const EmoTuneLogo(size: 130),
                    const SizedBox(height: 20),
                    Text(
                      'Let your mood decide your music',
                      style: GoogleFonts.manrope(
                        color: AppColors.textSecondary,
                        fontSize: 14,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                    const SizedBox(height: 48),
                    SizedBox(
                      width: 200,
                      child: EmoTuneSecondaryButton(
                        label: 'Continue',
                        onPressed: _continue,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
