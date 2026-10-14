import 'package:flutter/material.dart';

/// Fades and lifts [child] into place on its slot of a shared entrance run.
///
/// Slots are spaced [slotGap] apart on one controller so the whole screen
/// arrives as a single sequence rather than each widget animating on its own
/// clock. The interval is transformed directly instead of wrapping a
/// CurvedAnimation, so nothing here needs disposing.
class StaggerReveal extends StatelessWidget {
  const StaggerReveal({
    super.key,
    required this.controller,
    required this.slot,
    required this.child,
    this.dy = 16,
    this.slotGap = 0.17,
    this.riseSpan = 0.5,
  });

  final Animation<double> controller;
  final int slot;
  final Widget child;
  final double dy;
  final double slotGap;
  final double riseSpan;

  @override
  Widget build(BuildContext context) {
    final start = (slot * slotGap).clamp(0.0, 1.0);
    final end = (start + riseSpan).clamp(0.0, 1.0);

    return AnimatedBuilder(
      animation: controller,
      builder: (context, inner) {
        final t = start >= end
            ? 1.0
            : Interval(start, end, curve: Curves.easeOutCubic)
                .transform(controller.value);
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, dy * (1 - t)),
            child: inner,
          ),
        );
      },
      child: child,
    );
  }
}
