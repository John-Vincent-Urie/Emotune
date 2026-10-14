/// The support contacts bundled in the app so the support screen and the
/// check-in banner still list someone when the backend cannot be reached.
///
/// Same shape as `SupportResource.to_payload`. Owner decision, 2026-10-08:
/// 911 and the NCMH Crisis Hotline (backend migration 0004) are out of the
/// shown contacts while replacement numbers are sourced and verified -- see
/// backend migration 0006. That leaves no emergency/24-7-hotline entry here
/// for now, which is why the Music Cares description below no longer tells
/// people to "call emergency services first": there is nothing in this list
/// for that sentence to point at.
///
/// Do not add numbers here unless the project owner has verified them. Keep
/// this list in step with the backend migrations.
const List<Map<String, dynamic>> kBundledSupportContacts = [
  {
    'name': 'Music Cares Studio (Globe)',
    'kind': 'counselor',
    'kind_label': 'Therapist / counselor',
    'description': 'Therapist service. Not a 24/7 crisis line.',
    'phone': '09173255789',
  },
  {
    'name': 'Music Cares Studio (Smart)',
    'kind': 'counselor',
    'kind_label': 'Therapist / counselor',
    'description': 'Therapist service. Not a 24/7 crisis line.',
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
