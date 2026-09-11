import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';

/// The EmoTune mark: a conic teal/mint/lime ring around a pulsing six-bar
/// equalizer with a self-drawing smile underneath, optionally paired with
/// the shimmering "EmoTune" wordmark. This is the one shared implementation
/// -- the welcome screen's larger, ring-pinged version is built from the same
/// pieces via [EmoTuneMark] so the identity never drifts between screens.
class EmoTuneLogo extends StatefulWidget {
  const EmoTuneLogo({
    super.key,
    this.size = 100,
    this.showText = true,
    this.animate = true,
  });

  final double size;
  final bool showText;

  /// Set false for logos that appear many-at-once (list rows, etc.) where a
  /// continuously pulsing mark would be distracting rather than lively.
  final bool animate;

  @override
  State<EmoTuneLogo> createState() => _EmoTuneLogoState();
}

class _EmoTuneLogoState extends State<EmoTuneLogo>
    with TickerProviderStateMixin {
  late final AnimationController _pulse;
  late final AnimationController _shimmer;
  bool? _reduceMotion;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );
    _shimmer = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4200),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = !widget.animate || MediaQuery.of(context).disableAnimations;
    if (reduce == _reduceMotion) return;
    setState(() => _reduceMotion = reduce);
    if (reduce) {
      _pulse.stop();
      _shimmer.stop();
    } else {
      _pulse.repeat();
      _shimmer.repeat();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    _shimmer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = _reduceMotion ?? !widget.animate;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        EmoTuneMark(size: widget.size, pulse: _pulse, reduceMotion: reduce),
        if (widget.showText) ...[
          SizedBox(height: widget.size * 0.1),
          EmoTuneWordmark(
            shimmer: _shimmer,
            fontSize: widget.size * 0.28,
            reduceMotion: reduce,
          ),
        ],
      ],
    );
  }
}

/// Just the ring-and-equalizer mark, for callers (like the welcome screen)
/// that drive their own animation controllers and want the radar-ping rings
/// layered around it.
class EmoTuneMark extends StatelessWidget {
  const EmoTuneMark({
    super.key,
    required this.size,
    required this.pulse,
    this.reduceMotion = false,
    this.smileDraw,
  });

  final double size;
  final Animation<double> pulse;
  final bool reduceMotion;

  /// Optional 0..1 progress for the self-drawing smile stroke. Defaults to
  /// fully drawn, for the many places the logo just needs to sit still.
  final Animation<double>? smileDraw;

  static const List<double> _barHeights = [0.18, 0.28, 0.36, 0.32, 0.24, 0.16];

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const SweepGradient(
          startAngle: 0,
          endAngle: 2 * math.pi,
          colors: [AppColors.teal, AppColors.mint, AppColors.lime, AppColors.mint, AppColors.teal],
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.teal.withValues(alpha: 0.32),
            blurRadius: size * 0.32,
            spreadRadius: size * 0.02,
          ),
          BoxShadow(
            color: AppColors.lime.withValues(alpha: 0.16),
            blurRadius: size * 0.48,
            spreadRadius: size * 0.06,
          ),
        ],
      ),
      child: Stack(
        children: [
          Align(
            alignment: const Alignment(0, -0.30),
            child: _bars(),
          ),
          Positioned.fill(
            child: smileDraw == null
                ? CustomPaint(painter: _SmilePainter(progress: 1))
                : AnimatedBuilder(
                    animation: smileDraw!,
                    builder: (context, _) =>
                        CustomPaint(painter: _SmilePainter(progress: smileDraw!.value)),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _bars() {
    final barWidth = size * 0.055;
    final gap = size * 0.038;

    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        for (var i = 0; i < _barHeights.length; i++) ...[
          if (i > 0) SizedBox(width: gap),
          AnimatedBuilder(
            animation: pulse,
            builder: (context, child) {
              if (reduceMotion) return child!;
              final phase = pulse.value * 2 * math.pi + i * 0.7;
              return Transform.scale(
                scaleY: 0.62 + 0.38 * (0.5 + 0.5 * math.sin(phase)),
                child: child,
              );
            },
            child: Container(
              width: barWidth,
              height: size * _barHeights[i],
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(barWidth),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _SmilePainter extends CustomPainter {
  _SmilePainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    if (progress <= 0) return;

    final path = Path()
      ..moveTo(size.width * 0.30, size.height * 0.60)
      ..quadraticBezierTo(
        size.width * 0.50,
        size.height * 0.80,
        size.width * 0.70,
        size.height * 0.60,
      );

    final metric = path.computeMetrics().first;
    final drawn = metric.extractPath(0, metric.length * progress.clamp(0, 1));

    canvas.drawPath(
      drawn,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = size.width * 0.06,
    );
  }

  @override
  bool shouldRepaint(covariant _SmilePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

/// The shimmering "EmoTune" wordmark -- Fraunces italic with a teal/mint/lime
/// gradient that slides across the text on a loop.
class EmoTuneWordmark extends StatelessWidget {
  const EmoTuneWordmark({
    super.key,
    required this.shimmer,
    this.fontSize = 34,
    this.reduceMotion = false,
    this.color,
  });

  final Animation<double> shimmer;
  final double fontSize;
  final bool reduceMotion;

  /// Fallback solid color shown while the gradient shader mounts, and used
  /// verbatim when [reduceMotion] callers still want a static tint.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final text = Text(
      'EmoTune',
      style: GoogleFonts.fraunces(
        fontSize: fontSize,
        fontWeight: FontWeight.w600,
        fontStyle: FontStyle.italic,
        letterSpacing: 0.2,
        color: color ?? AppColors.textPrimary,
      ),
    );

    return AnimatedBuilder(
      animation: shimmer,
      builder: (context, child) {
        return ShaderMask(
          blendMode: BlendMode.srcIn,
          shaderCallback: (bounds) {
            final dx = reduceMotion ? bounds.width : shimmer.value * bounds.width;
            return const LinearGradient(
              colors: [AppColors.teal, AppColors.mint, AppColors.lime, AppColors.mint, AppColors.teal],
              tileMode: TileMode.mirror,
            ).createShader(
              Rect.fromLTWH(
                bounds.left - bounds.width + dx,
                bounds.top,
                bounds.width,
                bounds.height,
              ),
            );
          },
          child: child,
        );
      },
      child: text,
    );
  }
}
