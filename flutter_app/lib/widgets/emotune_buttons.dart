import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/app_theme.dart';

const double _kButtonHeight = 52;

/// The full-width teal/mint/lime gradient pill used for the app's primary
/// call to action -- "Create an account" on welcome, "Log in" / "Create
/// account" on the auth forms, and any other screen's main action.
class EmoTunePrimaryButton extends StatefulWidget {
  const EmoTunePrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.height = _kButtonHeight,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final double height;

  @override
  State<EmoTunePrimaryButton> createState() => _EmoTunePrimaryButtonState();
}

class _EmoTunePrimaryButtonState extends State<EmoTunePrimaryButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _shine;
  bool? _reduceMotion;

  @override
  void initState() {
    super.initState();
    _shine = AnimationController(vsync: this, duration: const Duration(milliseconds: 3800));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce == _reduceMotion) return;
    setState(() => _reduceMotion = reduce);
    if (reduce) {
      _shine.stop();
    } else {
      _shine.repeat();
    }
  }

  @override
  void dispose() {
    _shine.dispose();
    super.dispose();
  }

  bool get _disabled => widget.onPressed == null || widget.isLoading;

  @override
  Widget build(BuildContext context) {
    final reduce = _reduceMotion ?? false;

    return _PressFeedback(
      onTap: _disabled ? null : widget.onPressed,
      semanticLabel: widget.label,
      builder: (context, pressed, hovered) {
        return Opacity(
          opacity: _disabled && !widget.isLoading ? 0.4 : 1,
          child: Container(
            height: widget.height,
            width: double.infinity,
            decoration: BoxDecoration(
              gradient: AppColors.buttonGradient,
              borderRadius: BorderRadius.circular(widget.height / 2),
              boxShadow: [
                BoxShadow(
                  color: AppColors.mint.withValues(alpha: pressed ? 0.18 : 0.30),
                  blurRadius: 26,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(widget.height / 2),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  if (!reduce) _sweep(),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: widget.isLoading
                        ? const SizedBox(
                            key: ValueKey('loading'),
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.4,
                              valueColor: AlwaysStoppedAnimation(Color(0xFF06120D)),
                            ),
                          )
                        : Text(
                            widget.label,
                            key: const ValueKey('label'),
                            style: GoogleFonts.manrope(
                              color: const Color(0xFF06120D),
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.2,
                            ),
                          ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// A diagonal highlight crossing the pill in the first quarter of the
  /// loop, leaving a few seconds of rest before the next pass.
  Widget _sweep() {
    return Positioned.fill(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth;
          return AnimatedBuilder(
            animation: _shine,
            builder: (context, child) {
              final t = const Interval(0, 0.28, curve: Curves.easeInOut).transform(_shine.value);
              return Transform.translate(
                offset: Offset(-width * 0.4 + t * width * 1.6, 0),
                child: child,
              );
            },
            child: Transform.rotate(
              angle: 0.35,
              child: Container(
                width: 58,
                height: widget.height * 2.4,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.white.withValues(alpha: 0),
                      Colors.white.withValues(alpha: 0.42),
                      Colors.white.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// The outline pill used for secondary actions -- "Login" on welcome, "Back"
/// links, etc.
class EmoTuneSecondaryButton extends StatelessWidget {
  const EmoTuneSecondaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.height = _kButtonHeight,
  });

  final String label;
  final VoidCallback? onPressed;
  final double height;

  @override
  Widget build(BuildContext context) {
    return _PressFeedback(
      onTap: onPressed,
      semanticLabel: label,
      builder: (context, pressed, hovered) {
        final active = pressed || hovered;
        return Opacity(
          opacity: onPressed == null ? 0.4 : 1,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            height: height,
            width: double.infinity,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: active ? AppColors.mint.withValues(alpha: 0.12) : Colors.white.withValues(alpha: 0.02),
              borderRadius: BorderRadius.circular(height / 2),
              border: Border.all(
                color: active ? AppColors.mint.withValues(alpha: 0.7) : Colors.white.withValues(alpha: 0.22),
              ),
            ),
            child: Text(
              label,
              style: GoogleFonts.manrope(
                color: active ? AppColors.mint : AppColors.textPrimary,
                fontSize: 16,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.2,
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Shared press/hover plumbing: reports both states to [builder] and scales
/// the whole control down slightly while it is held.
class _PressFeedback extends StatefulWidget {
  const _PressFeedback({required this.builder, required this.onTap, required this.semanticLabel});

  final Widget Function(BuildContext context, bool pressed, bool hovered) builder;
  final VoidCallback? onTap;
  final String semanticLabel;

  @override
  State<_PressFeedback> createState() => _PressFeedbackState();
}

class _PressFeedbackState extends State<_PressFeedback> {
  bool _pressed = false;
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: widget.onTap != null,
      label: widget.semanticLabel,
      onTap: widget.onTap,
      // The visible label is a Text inside, so without this the button was
      // announced twice ("Get started, Get started").
      excludeSemantics: true,
      child: MouseRegion(
        cursor: widget.onTap == null ? MouseCursor.defer : SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onTap,
          onTapDown: widget.onTap == null ? null : (_) => setState(() => _pressed = true),
          onTapUp: widget.onTap == null ? null : (_) => setState(() => _pressed = false),
          onTapCancel: widget.onTap == null ? null : () => setState(() => _pressed = false),
          child: AnimatedScale(
            scale: _pressed ? 0.97 : 1,
            duration: const Duration(milliseconds: 120),
            curve: Curves.easeOut,
            child: widget.builder(context, _pressed, _hovered),
          ),
        ),
      ),
    );
  }
}
