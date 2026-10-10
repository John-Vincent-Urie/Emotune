import 'package:emotune/screens/widgets/song_count_line.dart';
import 'package:emotune/theme/app_theme.dart';
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

  testWidgets('uses the server total and the emotion display name',
      (tester) async {
    await pump(tester, {
      'emotion': 'happy',
      'emotion_info': {'id': 1, 'name': 'happy', 'display_name': 'Happy'},
      'total': 10,
    }, shown: 9);
    expect(find.text('10 therapist-approved songs for happy'), findsOneWidget);
  });

  testWidgets('falls back to the songs shown and the plain emotion',
      (tester) async {
    await pump(tester, {'emotion': 'calm'}, shown: 1);
    expect(find.text('1 therapist-approved song for calm'), findsOneWidget);
  });

  testWidgets('names the emotion the way the Discover tabs do', (tester) async {
    await pump(tester, {
      'emotion': 'motivational',
      'emotion_info': {
        'id': 4,
        'name': 'motivational',
        'display_name': 'Motivated',
      },
      'total': 10,
    });
    expect(find.text('10 therapist-approved songs for motivational'),
        findsOneWidget);
  });
}
