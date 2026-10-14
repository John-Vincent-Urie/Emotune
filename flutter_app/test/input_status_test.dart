import 'package:emotune/screens/home/input_status.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('clarifyMessageFor', () {
    test('accepted input shows songs, not a prompt', () {
      expect(clarifyMessageFor({'input_status': 'ok'}), isNull);
    });

    test('a server without input_status is treated as accepted', () {
      expect(clarifyMessageFor({'emotion': 'happy'}), isNull);
    });

    test("uses the server's message when it sends one", () {
      expect(
        clarifyMessageFor({
          'input_status': 'off_topic',
          'clarify_message': 'Tell me how you are feeling right now.',
        }),
        'Tell me how you are feeling right now.',
      );
    });

    test('falls back to the agreed wording per status', () {
      expect(clarifyMessageFor({'input_status': 'gibberish'}),
          kClarifyFallbackMessages['gibberish']);
      expect(clarifyMessageFor({'input_status': 'non_english'}),
          'Please describe how you feel in English.');
      expect(clarifyMessageFor({'input_status': 'unclear'}),
          'Please clarify what you feel right now.');
    });

    test('an unknown status still asks rather than guessing', () {
      expect(clarifyMessageFor({'input_status': 'something_new'}),
          kClarifyFallbackMessages['unclear']);
    });
  });
}
