import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../../theme/emotion_names.dart';

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
    // The therapist's name, as on the Discover tabs ("Motivated", not the
    // model key "motivational").
    final emotion = emotionDisplayName(
      result?['emotion']?.toString() ??
          (info is Map ? info['name']?.toString() : null),
      serverDisplayName: info is Map ? info['display_name'] : null,
    );
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
