import 'package:emotune/screens/widgets/song_count_line.dart';
import 'package:emotune/theme/app_theme.dart';
import 'package:emotune/theme/emotion_names.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pump(WidgetTester tester, Map<String, dynamic>? result,
      {int shown = 0}) {
    return tester.pumpWidget(MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(body: SongCountLine(result: result, shown: shown)),
    ));
  }

  testWidgets('uses the server total and display name', (tester) async {
    await pump(tester, {
      'emotion': 'motivational',
      'emotion_info': {
        'id': 4,
        'name': 'motivational',
        'display_name': 'Motivated',
      },
      'total': 10,
    }, shown: 9);
    expect(find.text('10 therapist-approved songs for motivated'),
        findsOneWidget);
  });

  testWidgets('falls back to the songs shown and the therapist name',
      (tester) async {
    await pump(tester, {'emotion': 'fear'}, shown: 1);
    expect(find.text('1 therapist-approved song for scared'), findsOneWidget);
  });

  test('every model key maps to the therapist name', () {
    expect(emotionDisplayName('motivational'), 'Motivated');
    expect(emotionDisplayName('fear'), 'Scared');
    expect(emotionDisplayName('depressing'), 'Depressed');
    expect(emotionDisplayName('surprising'), 'Surprised');
    expect(emotionDisplayName('happy'), 'Happy');
    expect(emotionDisplayName('calm', serverDisplayName: 'Calm'), 'Calm');
    expect(kEmotionDisplayNames, hasLength(13));
  });
}
