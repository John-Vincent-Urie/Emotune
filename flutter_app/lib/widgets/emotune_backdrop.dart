import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// The vignette + drifting glow blobs used behind onboarding-style screens
/// (splash, welcome, login/register). Self-contained: owns its own animation
/// controllers and respects `prefers-reduced-motion` on its own, so any
/// screen can drop it in as `Positioned.fill(child: EmoTuneBackdrop())`.
class EmoTuneBackdrop extends StatefulWidget {
  const EmoTuneBackdrop({super.key, this.showParticles = true});

  /// Particles are the most expensive part of the backdrop (a repainting
  /// CustomPainter); screens that layer a lot of scrolling content on top
  /// can turn them off and keep just the vignette and blobs.
  final bool showParticles;

  @override
  State<EmoTuneBackdrop> createState() => _EmoTuneBackdropState();
}

class _EmoTuneBackdropState extends State<EmoTuneBackdrop>
    with TickerProviderStateMixin {
  late final AnimationController _blobA;
  late final AnimationController _blobB;
  late final AnimationController _particles;
  late final List<_Particle> _particleField;
  bool? _reduceMotion;

  @override
  void initState() {
    super.initState();
    _blobA = AnimationController(vsync: this, duration: const Duration(milliseconds: 11000));
    _blobB = AnimationController(vsync: this, duration: const Duration(milliseconds: 13000));
    _particles = AnimationController(vsync: this, duration: const Duration(milliseconds: 24000));
    _particleField = _Particle.field(count: 13, random: math.Random(7));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce == _reduceMotion) return;
    setState(() => _reduceMotion = reduce);
    for (final controller in [_blobA, _blobB, _particles]) {
      if (reduce) {
        controller.stop();
        controller.value = 0;
      } else {
        controller.repeat();
      }
    }
  }

  @override
  void dispose() {
    _blobA.dispose();
    _blobB.dispose();
    _particles.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = _reduceMotion ?? false;

    return DecoratedBox(
      decoration: const BoxDecoration(color: AppColors.darkBg),
      child: Stack(
        children: [
          const Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0, -0.25),
                  radius: 1.1,
                  colors: [AppColors.vignetteInner, AppColors.vignetteOuter],
                ),
              ),
            ),
          ),
          _blob(
            animation: _blobA,
            color: AppColors.teal,
            anchor: const Alignment(-0.75, -0.7),
            travel: const Offset(46, 34),
            diameter: 320,
            reduceMotion: reduce,
          ),
          _blob(
            animation: _blobB,
            color: AppColors.lime,
            anchor: const Alignment(0.8, 0.65),
            travel: const Offset(-38, 44),
            diameter: 280,
            phase: math.pi / 3,
            reduceMotion: reduce,
          ),
          if (!reduce && widget.showParticles)
            Positioned.fill(
              child: RepaintBoundary(
                child: CustomPaint(
                  painter: _ParticlePainter(progress: _particles, particles: _particleField),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _blob({
    required Animation<double> animation,
    required Color color,
    required Alignment anchor,
    required Offset travel,
    required double diameter,
    required bool reduceMotion,
    double phase = 0,
  }) {
    final glow = IgnorePointer(
      child: Container(
        width: diameter,
        height: diameter,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              color.withValues(alpha: 0.20),
              color.withValues(alpha: 0.07),
              color.withValues(alpha: 0),
            ],
            stops: const [0, 0.45, 1],
          ),
        ),
      ),
    );

    if (reduceMotion) {
      return Align(alignment: anchor, child: glow);
    }

    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        final angle = animation.value * 2 * math.pi + phase;
        return Align(
          alignment: anchor,
          child: Transform.translate(
            offset: Offset(
              math.sin(angle) * travel.dx,
              math.cos(angle * 0.8) * travel.dy,
            ),
            child: child,
          ),
        );
      },
      child: glow,
    );
  }
}

class _Particle {
  const _Particle({
    required this.x,
    required this.radius,
    required this.speed,
    required this.drift,
    required this.phase,
  });

  final double x;
  final double radius;
  final double speed;
  final double drift;
  final double phase;

  static List<_Particle> field({required int count, required math.Random random}) {
    return List.generate(count, (_) {
      return _Particle(
        x: random.nextDouble(),
        radius: 0.8 + random.nextDouble() * 1.6,
        speed: 0.7 + random.nextDouble() * 0.8,
        drift: 8 + random.nextDouble() * 22,
        phase: random.nextDouble(),
      );
    });
  }
}

class _ParticlePainter extends CustomPainter {
  _ParticlePainter({required this.progress, required this.particles}) : super(repaint: progress);

  final Animation<double> progress;
  final List<_Particle> particles;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..style = PaintingStyle.fill;

    for (final particle in particles) {
      final t = (progress.value * particle.speed + particle.phase) % 1.0;
      final y = size.height * (1.05 - t * 1.1);
      final sway = math.sin(t * 2 * math.pi + particle.phase * 6) * particle.drift;
      final x = size.width * particle.x + sway;

      final opacity = math.sin(t * math.pi) * 0.35;
      if (opacity <= 0.01) continue;

      paint.color = Color.lerp(AppColors.teal, AppColors.lime, particle.x)!.withValues(alpha: opacity);
      canvas.drawCircle(Offset(x, y), particle.radius, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _ParticlePainter oldDelegate) => oldDelegate.particles != particles;
}
