/// The therapist's names for each emotion (docs/music.md), keyed by the
/// model's label. The API keeps the model keys ("motivational", "fear") as
/// identifiers; anything a person reads uses these names, so a tab, the song
/// count and a history card never call the same mood two different things.
const Map<String, String> kEmotionDisplayNames = {
  'happy': 'Happy',
  'sad': 'Sad',
  'angry': 'Angry',
  'motivational': 'Motivated',
  'fear': 'Scared',
  'depressing': 'Depressed',
  'nostalgic': 'Nostalgic',
  'romantic': 'Romantic',
  'lonely': 'Lonely',
  'calm': 'Calm',
  'stressed': 'Stressed',
  'surprising': 'Surprised',
  'mixed': 'Mixed',
};

/// [serverDisplayName] (the backend's `display_name`) when it sent one,
/// else the therapist's name for [key], else [key] capitalised.
String emotionDisplayName(String? key, {Object? serverDisplayName}) {
  final fromServer = serverDisplayName?.toString().trim() ?? '';
  if (fromServer.isNotEmpty) return fromServer;
  final normalized = key?.trim().toLowerCase() ?? '';
  if (normalized.isEmpty) return '';
  return kEmotionDisplayNames[normalized] ??
      '${normalized[0].toUpperCase()}${normalized.substring(1)}';
}
