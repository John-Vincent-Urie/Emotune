import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

/// "10 therapist-approved songs for happy" above a song grid.
///
/// The playlist is the therapist's whole list for the emotion, not a ranked
/// pick, so the count tells the student they are seeing all of it. Uses the
/// server's `total` when present, else the number of songs shown.
class SongCountLine extends StatelessWidget {
  const SongCountLine({super.key, required this.result, required this.shown});

  final Map<String, dynamic>? result;
  final int shown;

  @override
  Widget build(BuildContext context) {
    final rawTotal = result?['total'];
    final total = rawTotal is num ? rawTotal.toInt() : shown;
    final info = result?['emotion_info'];
    // The model's name ("motivational"), not music.md's display name
    // ("Motivated"): the Discover tabs and the result chip use the model's,
    // and the two disagree for four emotions.
    final emotion = (info is Map ? info['name'] : null)?.toString().trim() ??
        result?['emotion']?.toString().trim() ??
        '';
    final noun = total == 1 ? 'song' : 'songs';
    final label = emotion.isEmpty
        ? '$total therapist-approved $noun'
        : '$total therapist-approved $noun for ${emotion.toLowerCase()}';

    return Align(
      alignment: Alignment.centerLeft,
      child: Text(
        label,
        style: TextStyle(
          color: context.emoColors.textSecondary,
          fontSize: 12.5,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
