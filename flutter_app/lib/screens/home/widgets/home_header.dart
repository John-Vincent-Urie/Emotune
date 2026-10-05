import 'package:flutter/material.dart';

import '../../../theme/app_theme.dart';
import '../../../widgets/emotune_logo.dart';
import '../../../widgets/stagger_reveal.dart';

/// The brand block at the top of the home screen: the EmoTune mark sitting in
/// a slowly breathing halo, with the shimmering wordmark under it.
///
/// It stays put once the results come in -- the design keeps the header fixed
/// above the scrolling area rather than letting it scroll away -- so it is
/// built outside the home screen's [Expanded] body.
class HomeHeader extends StatefulWidget {
  const HomeHeader({
    super.key,
    required this.entrance,
    required this.reduceMotion,
  });

  /// Shared with the rest of the home screen so the whole page arrives as one
  /// sequence; the header takes the first slot.
  final Animation<double> entrance;
  final bool reduceMotion;

  @override
  State<HomeHeader> createState() => _HomeHeaderState();
}

class _HomeHeaderState extends State<HomeHeader> with TickerProviderStateMixin {
  static const double _markSize = 52;
  // The halo sits this far proud of the mark on every side. It is painted
  // outside the header's layout box rather than being sized into it, so the
  // glow never costs the orb, prompt and composer below it any height.
  static const double _haloBleed = 9;

  late final AnimationController _halo;
  late final AnimationController _pulse;
  late final AnimationController _shimmer;

  @override
  void initState() {
    super.initState();
    _halo = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );
    _shimmer = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4200),
    );
    _applyMotionPreference();
  }

  @override
  void didUpdateWidget(covariant HomeHeader oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reduceMotion != widget.reduceMotion) {
      _applyMotionPreference();
    }
  }

  void _applyMotionPreference() {
    if (widget.reduceMotion) {
      _halo.stop();
      _pulse.stop();
      _shimmer.stop();
      return;
    }
    // reverse: true so the halo eases out and back rather than snapping to its
    // smallest size every four seconds.
    _halo.repeat(reverse: true);
    _pulse.repeat();
    _shimmer.repeat();
  }

  @override
  void dispose() {
    _halo.dispose();
    _pulse.dispose();
    _shimmer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return StaggerReveal(
      controller: widget.entrance,
      slot: 0,
      dy: 10,
      child: Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: _markSize,
              height: _markSize,
              child: Stack(
                clipBehavior: Clip.none,
                alignment: Alignment.center,
                children: [
                  Positioned(
                    left: -_haloBleed,
                    top: -_haloBleed,
                    right: -_haloBleed,
                    bottom: -_haloBleed,
                    child: _breathingHalo(),
                  ),
                  EmoTuneMark(
                    size: _markSize,
                    pulse: _pulse,
                    reduceMotion: widget.reduceMotion,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 6),
            EmoTuneWordmark(
              shimmer: _shimmer,
              fontSize: 19,
              reduceMotion: widget.reduceMotion,
            ),
          ],
        ),
      ),
    );
  }

  Widget _breathingHalo() {
    final halo = DecoratedBox(
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [
            AppColors.teal.withValues(alpha: 0.35),
            AppColors.teal.withValues(alpha: 0.0),
          ],
          stops: const [0.0, 0.7],
        ),
      ),
    );

    if (widget.reduceMotion) {
      return Opacity(opacity: 0.7, child: halo);
    }
    return AnimatedBuilder(
      animation: _halo,
      builder: (context, child) {
        final t = Curves.easeInOut.transform(_halo.value);
        return Opacity(
          opacity: 0.7 + 0.3 * t,
          child: Transform.scale(scale: 1 + 0.18 * t, child: child),
        );
      },
      child: halo,
    );
  }
}
