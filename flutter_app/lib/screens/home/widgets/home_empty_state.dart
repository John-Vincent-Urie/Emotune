import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../models/mood_option.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/stagger_reveal.dart';

/// The centre of the home screen before the user has said anything: a
/// "listening" orb and a rotating suggestion line.
class HomeEmptyState extends StatefulWidget {
  const HomeEmptyState({
    super.key,
    required this.entrance,
    required this.reduceMotion,
  });

  /// Shared with the header so the screen arrives as one sequence.
  final Animation<double> entrance;
  final bool reduceMotion;

  @override
  State<HomeEmptyState> createState() => _HomeEmptyStateState();
}

class _HomeEmptyStateState extends State<HomeEmptyState>
    with TickerProviderStateMixin {
  static const Duration _promptInterval = Duration(milliseconds: 3500);

  late final AnimationController _orbPulse;
  late final AnimationController _ringSpin;
  Timer? _promptTimer;
  int _promptIndex = 0;

  @override
  void initState() {
    super.initState();
    _orbPulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    );
    _ringSpin = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 9),
    );
    _applyMotionPreference();
  }

  @override
  void didUpdateWidget(covariant HomeEmptyState oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reduceMotion != widget.reduceMotion) {
      _applyMotionPreference();
    }
  }

  void _applyMotionPreference() {
    _promptTimer?.cancel();
    if (widget.reduceMotion) {
      _orbPulse.stop();
      _ringSpin.stop();
      // A line of text that rewrites itself is motion too, so hold the first
      // suggestion rather than cycling.
      return;
    }
    _orbPulse.repeat(reverse: true);
    _ringSpin.repeat();
    _promptTimer = Timer.periodic(_promptInterval, (_) {
      if (!mounted) return;
      setState(() {
        _promptIndex = (_promptIndex + 1) % kPromptSuggestions.length;
      });
    });
  }

  @override
  void dispose() {
    _promptTimer?.cancel();
    _orbPulse.dispose();
    _ringSpin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        StaggerReveal(
          controller: widget.entrance,
          slot: 0,
          child: _orb(),
        ),
        const SizedBox(height: 26),
        StaggerReveal(
          controller: widget.entrance,
          slot: 1,
          child: _promptLine(colors),
        ),
      ],
    );
  }

  Widget _orb() {
    const orbSize = 90.0;
    const ringSize = orbSize + 26;

    final orb = Container(
      width: orbSize,
      height: orbSize,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const SweepGradient(
          colors: [
            AppColors.teal,
            AppColors.mint,
            AppColors.lime,
            AppColors.mint,
            AppColors.teal,
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.teal.withValues(alpha: 0.28),
            blurRadius: 30,
            spreadRadius: 2,
          ),
        ],
      ),
      child: const Center(child: _MiniEqualizer()),
    );

    return SizedBox(
      width: ringSize,
      height: ringSize,
      child: Stack(
        alignment: Alignment.center,
        children: [
          if (widget.reduceMotion)
            const _DashedRing(size: ringSize)
          else
            RotationTransition(
              turns: _ringSpin,
              child: const _DashedRing(size: ringSize),
            ),
          if (widget.reduceMotion)
            orb
          else
            AnimatedBuilder(
              animation: _orbPulse,
              builder: (context, child) => Transform.scale(
                // Shallow on purpose: the orb should read as breathing, not
                // throbbing.
                scale: 0.94 + 0.06 * Curves.easeInOut.transform(_orbPulse.value),
                child: child,
              ),
              child: orb,
            ),
        ],
      ),
    );
  }

  Widget _promptLine(EmoTuneColors colors) {
    final text = Text(
      kPromptSuggestions[_promptIndex],
      key: ValueKey(_promptIndex),
      textAlign: TextAlign.center,
      style: TextStyle(
        color: colors.textSecondary,
        fontSize: 15,
        height: 1.4,
      ),
    );

    if (widget.reduceMotion) {
      return text;
    }
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 420),
      child: text,
    );
  }

}

/// Four white bars inside the orb, sized to read at 90px.
class _MiniEqualizer extends StatelessWidget {
  const _MiniEqualizer();

  static const List<double> _heights = [14, 24, 19, 11];

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        for (var i = 0; i < _heights.length; i++) ...[
          if (i > 0) const SizedBox(width: 5),
          Container(
            width: 5,
            height: _heights[i],
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(5),
            ),
          ),
        ],
      ],
    );
  }
}

class _DashedRing extends StatelessWidget {
  const _DashedRing({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.square(size),
      painter: _DashedRingPainter(
        color: context.emoColors.textSecondary.withValues(alpha: 0.45),
      ),
    );
  }
}

class _DashedRingPainter extends CustomPainter {
  _DashedRingPainter({required this.color});

  final Color color;

  static const int _dashCount = 36;
  static const double _dashFraction = 0.55;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..strokeCap = StrokeCap.round;

    final rect = Rect.fromLTWH(0.5, 0.5, size.width - 1, size.height - 1);
    const sweep = (2 * math.pi) / _dashCount;
    for (var i = 0; i < _dashCount; i++) {
      canvas.drawArc(
        rect,
        i * sweep,
        sweep * _dashFraction,
        false,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _DashedRingPainter oldDelegate) =>
      oldDelegate.color != color;
}

