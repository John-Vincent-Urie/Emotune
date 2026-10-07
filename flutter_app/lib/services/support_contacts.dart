/// The support contacts the project owner verified on 2026-10-04, bundled in
/// the app so the support screen and the check-in banner still list them when
/// the backend cannot be reached.
///
/// Same shape (SupportResource.to_payload) and order as backend migrations
/// 0003/0004: emergency first, then the 24/7 hotline, then the therapist
/// practice, which does not answer at 2am.
///
/// Do not add numbers here unless the project owner has verified them. Keep
/// this list in step with those migrations.
const List<Map<String, dynamic>> kBundledSupportContacts = [
  {
    'name': 'Emergency services (911)',
    'kind': 'emergency',
    'kind_label': 'Emergency services',
    'description': 'If you or someone else is in immediate danger, call 911 now.',
    'phone': '911',
    'hours': '24/7',
  },
  {
    'name': 'NCMH Crisis Hotline',
    'kind': 'hotline',
    'kind_label': 'Crisis hotline',
    'description': 'National Center for Mental Health crisis line. Talk to '
        'someone any time, day or night.',
    'phone': '1553',
    'hours': '24/7',
  },
  {
    'name': 'Music Cares Studio (Globe)',
    'kind': 'counselor',
    'kind_label': 'Therapist / counselor',
    'description': 'Therapist service. Not a 24/7 crisis line -- if you are in '
        'immediate danger, call emergency services first.',
    'phone': '09173255789',
  },
  {
    'name': 'Music Cares Studio (Smart)',
    'kind': 'counselor',
    'kind_label': 'Therapist / counselor',
    'description': 'Therapist service. Not a 24/7 crisis line -- if you are in '
        'immediate danger, call emergency services first.',
    'phone': '09189296012',
  },
];

/// [resources] from a server response when it has any, otherwise the bundled
/// list -- a safety surface must never render with no one to call.
List<Map<String, dynamic>> supportContactsOrBundled(List<dynamic>? resources) {
  final fromServer = (resources ?? const [])
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .where((item) => (item['name']?.toString().trim() ?? '').isNotEmpty)
      .toList();
  if (fromServer.isNotEmpty) {
    return fromServer;
  }
  return kBundledSupportContacts
      .map((item) => Map<String, dynamic>.from(item))
      .toList();
}

/// A `tel:` URI for [phone], keeping only digits and a leading plus.
Uri dialUri(String phone) =>
    Uri(scheme: 'tel', path: phone.replaceAll(RegExp(r'[^0-9+]'), ''));
