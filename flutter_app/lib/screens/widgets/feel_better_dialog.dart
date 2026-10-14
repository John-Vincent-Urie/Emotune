import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/player_provider.dart';
import '../../theme/app_theme.dart';

class FeelBetterDialog extends StatefulWidget {
  const FeelBetterDialog({super.key, required this.data});

  final Map<String, dynamic> data;

  @override
  State<FeelBetterDialog> createState() => _FeelBetterDialogState();
}

class _FeelBetterDialogState extends State<FeelBetterDialog> {
  bool _submitting = false;

  @override
  Widget build(BuildContext context) {
    final message = widget.data['message']?.toString().trim().isNotEmpty == true
        ? widget.data['message']!.toString().trim()
        : 'Are you feeling better right now?';
    final hasRecoveryPlan = widget.data['recovery_plan'] is Map;
    final positiveLabel = hasRecoveryPlan ? "I'm fine now" : 'This is working';
    final negativeLabel = hasRecoveryPlan ? 'Not yet' : 'Keep checking in';
    final subtitle = hasRecoveryPlan
        ? 'We can keep supporting this mood, or switch to a lighter recovery mix.'
        : 'We can keep the session going and check in again later, or lock this lane in and stop interrupting.';

    return Dialog(
      backgroundColor: AppColors.darkCard,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🌱', style: TextStyle(fontSize: 38)),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.68),
                fontSize: 13,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 22),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _submitting ? null : () => _submit(false),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white70,
                      side: const BorderSide(color: Colors.white24),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                      ),
                    ),
                    child: _submitting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white70,
                            ),
                          )
                        : Text(negativeLabel),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _submitting ? null : () => _submit(true),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.accent,
                      foregroundColor: Colors.black,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                      ),
                    ),
                    child: Text(positiveLabel),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _submit(bool feltBetter) async {
    setState(() => _submitting = true);
    try {
      final result = await context.read<PlayerProvider>().respondFeelBetter(feltBetter);
      if (!mounted) {
        return;
      }
      Navigator.pop(context, result);
    } catch (_) {
      if (!mounted) {
        return;
      }
      Navigator.pop(context);
    }
  }
}
