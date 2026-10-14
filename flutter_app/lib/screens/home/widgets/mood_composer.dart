import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../theme/app_theme.dart';

/// The prompt field and send button that sit above the tab bar.
///
/// Deliberately not part of the entrance sequence: the composer is the thing
/// the user came to use, so it is present from the first frame.
class MoodComposer extends StatefulWidget {
  const MoodComposer({
    super.key,
    required this.controller,
    required this.isBusy,
    required this.onSubmit,
    required this.reduceMotion,
  });

  final TextEditingController controller;
  final bool isBusy;
  final VoidCallback onSubmit;
  final bool reduceMotion;

  @override
  State<MoodComposer> createState() => _MoodComposerState();
}

class _MoodComposerState extends State<MoodComposer>
    with SingleTickerProviderStateMixin {
  final FocusNode _focusNode = FocusNode();
  late final AnimationController _sendPulse;

  @override
  void initState() {
    super.initState();
    _sendPulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 260),
    );
    _focusNode.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _sendPulse.dispose();
    super.dispose();
  }

  void _handleSend() {
    if (widget.isBusy) return;
    if (!widget.reduceMotion) {
      _sendPulse.forward(from: 0);
    }
    widget.onSubmit();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final focused = _focusNode.hasFocus;
    final isCompact = MediaQuery.sizeOf(context).width < 390;
    final buttonSize = isCompact ? 46.0 : 50.0;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        isCompact ? 12 : 16,
        8,
        isCompact ? 12 : 16,
        10,
      ),
      child: Row(
        // The field grows upward for longer feelings; the send button stays
        // level with its last line.
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: AnimatedContainer(
              duration: widget.reduceMotion
                  ? Duration.zero
                  : const Duration(milliseconds: 220),
              curve: Curves.easeOut,
              decoration: BoxDecoration(
                color: colors.inputBackground,
                borderRadius: BorderRadius.circular(26),
                border: Border.all(
                  color: focused
                      ? colors.accentText.withValues(alpha: 0.8)
                      : colors.divider,
                ),
                boxShadow: focused
                    ? [
                        BoxShadow(
                          color: AppColors.teal.withValues(alpha: 0.22),
                          blurRadius: 18,
                          spreadRadius: 1,
                        ),
                      ]
                    : null,
              ),
              child: TextField(
                controller: widget.controller,
                focusNode: _focusNode,
                style: TextStyle(color: colors.textPrimary, fontSize: 15),
                cursorColor: colors.accentText,
                // Wraps up to four lines, then scrolls. The keyboard keeps its
                // Send key: a feeling is one message, not a document.
                minLines: 1,
                maxLines: 4,
                keyboardType: TextInputType.text,
                decoration: InputDecoration(
                  // The theme fills inputs; here that painted a square over
                  // the rounded pill behind it.
                  filled: false,
                  hintText: 'I feel......',
                  hintStyle: TextStyle(
                    color: colors.textSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: isCompact ? 16 : 18,
                    vertical: 14,
                  ),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _handleSend(),
              ),
            ),
          ),
          SizedBox(width: isCompact ? 8 : 10),
          Semantics(
            button: true,
            label: 'Send',
            child: GestureDetector(
              onTap: widget.isBusy ? null : _handleSend,
              child: AnimatedBuilder(
                animation: _sendPulse,
                builder: (context, child) {
                  // One out-and-back kick: grow slightly and tilt, then settle.
                  final t = math.sin(_sendPulse.value * math.pi);
                  return Transform.rotate(
                    angle: t * 0.28,
                    child: Transform.scale(scale: 1 + t * 0.16, child: child),
                  );
                },
                child: Container(
                  width: buttonSize,
                  height: buttonSize,
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
                        color: AppColors.mint.withValues(alpha: 0.34),
                        blurRadius: 16,
                        offset: const Offset(0, 5),
                      ),
                    ],
                  ),
                  child: widget.isBusy
                      ? Padding(
                          padding: EdgeInsets.all(isCompact ? 13 : 14),
                          child: const CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Color(0xFF06120D),
                          ),
                        )
                      : Icon(
                          Icons.send_rounded,
                          color: const Color(0xFF06120D),
                          size: isCompact ? 19 : 21,
                        ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
