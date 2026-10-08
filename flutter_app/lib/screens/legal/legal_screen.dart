import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

enum LegalDoc { terms, privacy }

/// The Terms of Use and Privacy Policy, shipped inside the app.
///
/// They used to be links to emotune.app, which does not resolve, while
/// Register required agreeing to them -- users were asked to accept pages
/// they could not read.
///
/// DRAFT: the text below was written by the dev team for the project owner to
/// review. Items in [brackets] need the owner's answer before release, and the
/// banner at the top must go once the text is approved.
class LegalScreen extends StatelessWidget {
  const LegalScreen({super.key, required this.doc});

  final LegalDoc doc;

  static Future<void> open(BuildContext context, LegalDoc doc) {
    return Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => LegalScreen(doc: doc)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.emoColors;
    final isTerms = doc == LegalDoc.terms;
    final sections = isTerms ? _termsSections : _privacySections;

    return Scaffold(
      backgroundColor: colors.background,
      appBar: AppBar(
        backgroundColor: colors.background,
        foregroundColor: colors.textPrimary,
        elevation: 0,
        title: Text(isTerms ? 'Terms of Use' : 'Privacy Policy'),
      ),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: colors.safety),
              ),
              child: Text(
                'DRAFT: not yet reviewed by the EmoTune team. '
                'Last updated $_lastUpdated.',
                style: TextStyle(
                  color: colors.safety,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(height: 16),
            for (final section in sections) ...[
              Semantics(
                header: true,
                child: Text(
                  section.heading,
                  style: TextStyle(
                    color: colors.textPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 6),
              for (final paragraph in section.paragraphs) ...[
                Text(
                  paragraph,
                  style: TextStyle(
                    color: colors.textPrimary,
                    fontSize: 14,
                    height: 1.55,
                  ),
                ),
                const SizedBox(height: 8),
              ],
              const SizedBox(height: 10),
            ],
          ],
        ),
      ),
    );
  }
}

const String _lastUpdated = '6 October 2026';

class _Section {
  const _Section(this.heading, this.paragraphs);

  final String heading;
  final List<String> paragraphs;
}

const List<_Section> _termsSections = [
  _Section('What EmoTune is', [
    'EmoTune suggests music based on how you say you feel. It is a student '
        'capstone project [project owner: add school and team name].',
    'EmoTune is not a medical, counseling or emergency service, and it does '
        'not diagnose or treat anything. Music suggestions are not therapy.',
  ]),
  _Section('If you are in danger', [
    'If you or someone else is in immediate danger, contact your local '
        'emergency services right away. [Project owner: add verified '
        'emergency and crisis-line numbers here once sourced.]',
    'EmoTune checks messages for signs that someone may be at risk and, if it '
        'finds them, shows support contacts instead of music. This check can '
        'miss things. Never rely on EmoTune to notice that you need help.',
  ]),
  _Section('Your account', [
    'You need an email address and a password to use EmoTune. Keep your '
        'password private; you are responsible for what happens under your '
        'account.',
    'Please do not use EmoTune to harass anyone, to try to break or overload '
        'the service, or to get at other people\'s data.',
  ]),
  _Section('Spotify', [
    'Connecting Spotify is optional. If you connect it, Spotify\'s own terms '
        'apply to your use of Spotify, and playback depends on your Spotify '
        'account.',
  ]),
  _Section('Changes and ending', [
    'This is a student project and may change, pause or shut down. We will '
        'show updated terms in the app when they change.',
    '[Project owner: how users close their account, and a contact address '
        'for questions.]',
  ]),
];

const List<_Section> _privacySections = [
  _Section('What we collect', [
    'Account: your display name, email address and password. The password is '
        'stored only as a secure hash, never as the password itself.',
    'What you write: the feelings you type, the emotion EmoTune detects, its '
        'reply and the songs it suggested. These are saved to your history so '
        'you can see them on the History tab.',
    'Listening: songs you favorite, how long you listen, and whether you said '
        'you felt better, used to improve suggestions.',
    'Spotify: if you connect Spotify, we store the access tokens Spotify gives '
        'us so EmoTune can play music for you.',
  ]),
  _Section('Who else sees your text', [
    'Google Gemini: to choose songs, EmoTune may send what you typed, the '
        'detected emotion and your preferred artists to Google\'s Gemini AI '
        'service. '
        'These requests contain the text only, not your name, email or '
        'account ID. Google handles that data under its own terms.',
    'Spotify: song searches and playback go through Spotify.',
    'We do not sell your data, and we do not share it with advertisers.',
  ]),
  _Section('Safety checks', [
    'When EmoTune\'s safety check shows support contacts, it counts that this '
        'happened. That count does not include what you wrote or who you are.',
  ]),
  _Section('Your choices', [
    'Personalization: you can turn off "Mood-based personalization" in your '
        'profile.',
    'Private sessions: turn off "Train on this session" before you write, and '
        'that session is not used to train suggestions.',
    '[Project owner: there is no in-app way yet to delete your history or '
        'account. Say how users can ask for deletion, and how long data is '
        'kept.]',
  ]),
  _Section('Contact', [
    '[Project owner: add a contact email for privacy questions.]',
  ]),
];
