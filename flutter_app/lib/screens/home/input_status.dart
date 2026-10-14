/// What /api/analyze/ said about the text itself, before any emotion.
///
/// The server refuses to guess an emotion for gibberish, non-English text,
/// text that is not about the user's own feelings, or text the model is
/// unsure about. It then sends `input_status` other than `ok`, no songs and a
/// `clarify_message` asking the user to try again.
const Map<String, String> kClarifyFallbackMessages = {
  'gibberish':
      "I couldn't understand that. Please tell me how you are feeling right now.",
  'non_english': 'Please describe how you feel in English.',
  'off_topic': 'Tell me how you are feeling right now.',
  'unclear': 'Please clarify what you feel right now.',
};

/// The prompt to show instead of songs, or null when the input was accepted
/// (or the server predates `input_status`, which the app treats as accepted).
String? clarifyMessageFor(Map<String, dynamic> result) {
  final status = result['input_status']?.toString().trim() ?? '';
  if (status.isEmpty || status == 'ok') {
    return null;
  }
  final message = result['clarify_message']?.toString().trim() ?? '';
  if (message.isNotEmpty) {
    return message;
  }
  return kClarifyFallbackMessages[status] ??
      kClarifyFallbackMessages['unclear'];
}
