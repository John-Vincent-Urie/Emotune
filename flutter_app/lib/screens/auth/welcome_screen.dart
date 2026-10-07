import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../theme/app_theme.dart';
import '../legal/legal_screen.dart';
import '../../widgets/emotune_backdrop.dart';
import '../../widgets/emotune_buttons.dart';
import '../../widgets/emotune_logo.dart';

// Placeholders until the documents are hosted -- swap for the real URLs.
/// Entrance order. Each element rises [_stagger] after the one before it, so
/// the eye is led logo -> name -> promise -> action instead of being handed
/// the whole screen at once.
const int _revealLogo = 0;
const int _revealWordmark = 1;
const int _revealTagline = 2;
const int _revealButtons = 3;
const int _revealFinePrint = 4;

const Duration _entranceDuration = Duration(milliseconds: 1400);
const double _entranceLeadIn = 150 / 1400; // first element waits 150ms
const double _stagger = 150 / 1400;
const double _rise = 450 / 1400;

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with TickerProviderStateMixin {
  late final AnimationController _entrance;
  late final AnimationController _pulse; // equaliser bars
  late final AnimationController _ping; // radar rings
  late final AnimationController _shimmer; // wordmark gradient

  late final List<AnimationController> _loops;
  late final CurvedAnimation _smileDraw;
  late final List<CurvedAnimation> _reveals;

  bool? _reduceMotion;
  bool _entranceStarted = false;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(vsync: this, duration: _entranceDuration);
    _pulse = _loop(1600);
    _ping = _loop(3200);
    _shimmer = _loop(4200);
    _loops = [_pulse, _ping, _shimmer];

    // The smile starts drawing while the logo is still settling, so the mark
    // completes itself rather than arriving in two separate beats.
    _smileDraw = CurvedAnimation(
      parent: _entrance,
      curve: const Interval(0.21, 0.55, curve: Curves.easeOutCubic),
    );

    _reveals = List.generate(5, (index) {
      final start = _entranceLeadIn + index * _stagger;
      return CurvedAnimation(
        parent: _entrance,
        curve: Interval(start, start + _rise, curve: Curves.easeOutCubic),
      );
    });
  }

  AnimationController _loop(int ms) =>
      AnimationController(vsync: this, duration: Duration(milliseconds: ms));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce == _reduceMotion) return;
    _reduceMotion = reduce;

    if (reduce) {
      for (final controller in _loops) {
        controller.stop();
        controller.value = 0;
      }
      _entrance.value = 1;
      _entranceStarted = true;
    } else {
      for (final controller in _loops) {
        controller.repeat();
      }
      if (!_entranceStarted) {
        _entranceStarted = true;
        _entrance.forward();
      } else {
        _entrance.value = 1;
      }
    }
  }

  @override
  void dispose() {
    _smileDraw.dispose();
    for (final reveal in _reveals) {
      reveal.dispose();
    }
    _entrance.dispose();
    for (final controller in _loops) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = _reduceMotion ?? false;

    return Scaffold(
      backgroundColor: AppColors.darkBg,
      body: Stack(
        children: [
          const Positioned.fill(child: EmoTuneBackdrop()),
          Positioned.fill(
            child: SafeArea(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  return SingleChildScrollView(
                    child: ConstrainedBox(
                      constraints:
                          BoxConstraints(minHeight: constraints.maxHeight),
                      child: Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 400),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 32, vertical: 40),
                            child: _content(reduce),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _content(bool reduce) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _reveal(
          index: _revealLogo,
          scaleIn: true,
          child: _RingedLogoMark(
            size: 104,
            pulse: _pulse,
            ping: _ping,
            smileDraw: _smileDraw,
            reduceMotion: reduce,
          ),
        ),
        const SizedBox(height: 26),
        _reveal(
          index: _revealWordmark,
          child: EmoTuneWordmark(shimmer: _shimmer, reduceMotion: reduce),
        ),
        const SizedBox(height: 14),
        _reveal(
          index: _revealTagline,
          child: Text(
            'Turn what you feel into what you play. '
            'Your mood, matched to music.',
            textAlign: TextAlign.center,
            style: GoogleFonts.manrope(
              color: AppColors.textSecondary,
              fontSize: 15,
              height: 1.5,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        const SizedBox(height: 44),
        _reveal(
          index: _revealButtons,
          child: Column(
            children: [
              EmoTunePrimaryButton(
                label: 'Create an account',
                onPressed: () => Navigator.pushNamed(context, '/register'),
              ),
              const SizedBox(height: 14),
              EmoTuneSecondaryButton(
                label: 'Login',
                onPressed: () => Navigator.pushNamed(context, '/login'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),
        _reveal(
          index: _revealFinePrint,
          child: _FinePrint(
            onTermsTap: () => LegalScreen.open(context, LegalDoc.terms),
            onPrivacyTap: () => LegalScreen.open(context, LegalDoc.privacy),
          ),
        ),
      ],
    );
  }

  /// Fades a single element up into place on its slot in the entrance
  /// sequence. [scaleIn] is for the logo, which grows rather than slides.
  Widget _reveal({
    required int index,
    required Widget child,
    bool scaleIn = false,
  }) {
    final animation = _reveals[index];

    return AnimatedBuilder(
      animation: animation,
      builder: (context, inner) {
        final t = animation.value;
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, scaleIn ? 0 : 16 * (1 - t)),
            child: scaleIn
                ? Transform.scale(scale: 0.88 + 0.12 * t, child: inner)
                : inner,
          ),
        );
      },
      child: child,
    );
  }
}

/// The welcome screen's take on the shared [EmoTuneMark]: wrapped in two
/// staggered radar-ping rings that expand and fade on a loop. Kept local
/// since no other screen wants the ping treatment.
class _RingedLogoMark extends StatelessWidget {
  const _RingedLogoMark({
    required this.size,
    required this.pulse,
    required this.ping,
    required this.smileDraw,
    required this.reduceMotion,
  });

  final double size;
  final Animation<double> pulse;
  final Animation<double> ping;
  final Animation<double> smileDraw;
  final bool reduceMotion;

  @override
  Widget build(BuildContext context) {
    final ringSize = size * 1.5;

    return SizedBox(
      width: ringSize,
      height: ringSize,
      child: Stack(
        alignment: Alignment.center,
        children: [
          if (!reduceMotion) ...[
            _ring(delay: 0),
            _ring(delay: 0.5),
          ],
          EmoTuneMark(
            size: size,
            pulse: pulse,
            smileDraw: smileDraw,
            reduceMotion: reduceMotion,
          ),
        ],
      ),
    );
  }

  Widget _ring({required double delay}) {
    return AnimatedBuilder(
      animation: ping,
      builder: (context, child) {
        final t = (ping.value + delay) % 1.0;
        final eased = Curves.easeOut.transform(t);
        return Opacity(
          opacity: (1 - eased) * 0.4,
          child: Transform.scale(scale: 1 + eased * 0.5, child: child),
        );
      },
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.mint.withValues(alpha: 0.55), width: 1),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Fine print
// ---------------------------------------------------------------------------

class _FinePrint extends StatelessWidget {
  const _FinePrint({required this.onTermsTap, required this.onPrivacyTap});

  final VoidCallback onTermsTap;
  final VoidCallback onPrivacyTap;

  @override
  Widget build(BuildContext context) {
    final base = GoogleFonts.manrope(
      color: AppColors.textFine,
      fontSize: 12,
      height: 1.5,
    );

    // Separate widgets rather than one Text.rich with tap recognizers: on web
    // with accessibility on, the two inline links collapsed into one node and
    // both opened the privacy policy.
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text('By continuing you agree to our ', style: base),
        _FineLink(label: 'terms', style: base, onTap: onTermsTap),
        Text(' and ', style: base),
        _FineLink(label: 'privacy policy', style: base, onTap: onPrivacyTap),
      ],
    );
  }
}

class _FineLink extends StatelessWidget {
  const _FineLink({
    required this.label,
    required this.style,
    required this.onTap,
  });

  final String label;
  final TextStyle style;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      link: true,
      label: label,
      onTap: onTap,
      excludeSemantics: true,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Padding(
          // A taller hit area than the 18px line, without moving the text.
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(
            label,
            style: style.copyWith(
              color: AppColors.textSecondary,
              decoration: TextDecoration.underline,
              decorationColor: AppColors.textSecondary.withValues(alpha: 0.5),
            ),
          ),
        ),
      ),
    );
  }
}
