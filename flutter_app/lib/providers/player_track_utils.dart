/// Pure, stateless helpers for normalizing and comparing track/session data
/// used by [PlayerProvider]. Extracted out of the provider because none of
/// these functions read or mutate player state — they only transform their
/// arguments — unlike the rest of the provider, which is a single cohesive
/// real-time playback state machine (Spotify remote sync, local preview
/// playback, and queue/session tracking all read and write the same core
/// fields, so it isn't safely splittable the same way).
const Set<String> supportedSpotifyItemTypes = {
  'track',
  'playlist',
  'album',
  'artist',
  'episode',
  'show',
};

Map<String, dynamic> normalizeTrack(Map<String, dynamic> rawTrack) {
  final track = Map<String, dynamic>.from(rawTrack);
  final rawUri = track['uri']?.toString().trim() ?? '';
  final rawSpotifyUrl = track['spotify_url']?.toString().trim() ?? '';
  final rawType = track['item_type']?.toString().trim() ?? '';
  final rawId = track['id']?.toString().trim() ?? '';

  var itemType = rawType;
  var itemId = rawId;
  var uri = rawUri;
  var spotifyUrl = rawSpotifyUrl;

  if (uri.startsWith('spotify:')) {
    final parts = uri.split(':');
    if (parts.length >= 3) {
      itemType = itemType.isNotEmpty ? itemType : parts[1];
      itemId = itemId.isNotEmpty ? itemId : parts[2];
    }
  }

  if (spotifyUrl.isNotEmpty) {
    final parsedUri = Uri.tryParse(spotifyUrl);
    final segments = parsedUri?.pathSegments ?? const <String>[];
    final parsedType = segments.isNotEmpty ? segments[0] : '';
    if ((parsedUri?.host ?? '').contains('spotify.com') &&
        segments.length >= 2 &&
        supportedSpotifyItemTypes.contains(parsedType)) {
      itemType = itemType.isNotEmpty ? itemType : parsedType;
      itemId = itemId.isNotEmpty ? itemId : segments[1];
    }
  }

  if (uri.isEmpty &&
      itemId.isNotEmpty &&
      (itemType.isEmpty || supportedSpotifyItemTypes.contains(itemType))) {
    final resolvedType = itemType.isNotEmpty ? itemType : 'track';
    uri = 'spotify:$resolvedType:$itemId';
  }

  if (spotifyUrl.isEmpty &&
      itemId.isNotEmpty &&
      (itemType.isEmpty || supportedSpotifyItemTypes.contains(itemType))) {
    final resolvedType = itemType.isNotEmpty ? itemType : 'track';
    spotifyUrl = 'https://open.spotify.com/$resolvedType/$itemId';
  }

  track['id'] = itemId.isNotEmpty ? itemId : (uri.isNotEmpty ? uri : rawId);
  track['item_type'] = itemType.isNotEmpty ? itemType : 'track';
  track['uri'] = uri;
  track['spotify_url'] = spotifyUrl;
  return track;
}

bool isContainerType(String itemType) {
  return {'playlist', 'album', 'artist', 'show', 'collection'}
      .contains(itemType.trim().toLowerCase());
}

bool isContainerItem(Map<String, dynamic> track) {
  final itemType = track['item_type']?.toString() ?? '';
  return isContainerType(itemType);
}

List<Map<String, dynamic>> normalizeTrackList(List<dynamic> rawTracks) {
  return rawTracks
      .whereType<Map>()
      .map((track) => normalizeTrack(Map<String, dynamic>.from(track)))
      .where((track) {
    final uri = track['uri']?.toString().trim() ?? '';
    final previewUrl = track['preview_url']?.toString().trim() ?? '';
    return uri.isNotEmpty || previewUrl.isNotEmpty;
  }).toList();
}

int safeInt(Object? value, [int defaultValue = 0]) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '') ?? defaultValue;
}

Map<String, dynamic>? normalizeObjectMap(dynamic value) {
  if (value is! Map) {
    return null;
  }
  return Map<String, dynamic>.from(value);
}

String normalizeOutcomeMode(String? value) {
  switch (value?.trim().toLowerCase()) {
    case 'calm_me_down':
    case 'help_me_focus':
    case 'lift_me_up':
    case 'sleep':
      return value!.trim().toLowerCase();
    default:
      return 'match_mood';
  }
}

Map<String, dynamic> normalizeTasteProfile(
  dynamic value, {
  bool? trainOnThisSession,
}) {
  final raw =
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
  final familiarity =
      raw['familiarity']?.toString().trim().toLowerCase() ?? 'balanced';
  return <String, dynamic>{
    'familiarity': switch (familiarity) {
      'familiar' => 'familiar',
      'discovery' => 'discovery',
      _ => 'balanced',
    },
    'prefer_instrumental': raw['prefer_instrumental'] == true,
    'train_session': trainOnThisSession ?? (raw['train_session'] != false),
  };
}

String trackIdentity(Map<String, dynamic> rawTrack) {
  final track = normalizeTrack(rawTrack);
  final itemType = track['item_type']?.toString().trim() ?? 'track';
  final trackId = track['id']?.toString().trim() ?? '';
  if (trackId.isNotEmpty) {
    return '$itemType:$trackId';
  }
  final uri = track['uri']?.toString().trim() ?? '';
  if (uri.isNotEmpty) {
    return uri;
  }
  return track['spotify_url']?.toString().trim() ?? '';
}

List<Map<String, dynamic>> mergeTrackLists(
  List<dynamic> currentTracks,
  List<dynamic> incomingTracks,
) {
  final merged = <Map<String, dynamic>>[];
  final seenKeys = <String>{};

  void appendAll(List<dynamic> tracks) {
    for (final rawTrack in tracks.whereType<Map>()) {
      final normalizedTrack =
          normalizeTrack(Map<String, dynamic>.from(rawTrack));
      final identity = trackIdentity(normalizedTrack);
      if (identity.isEmpty || seenKeys.contains(identity)) {
        continue;
      }
      seenKeys.add(identity);
      merged.add(normalizedTrack);
    }
  }

  appendAll(currentTracks);
  appendAll(incomingTracks);
  return merged;
}

String composeSpotifyControlMessage(
  Map<String, dynamic> result, {
  required String defaultMessage,
}) {
  final recommendedAction =
      result['recommended_action']?.toString().trim() ?? '';
  final spotifyError = result['spotify_error'];
  final spotifyMessage = spotifyError is Map
      ? spotifyError['error']?.toString().trim() ?? ''
      : '';
  final blockingIssue = result['blocking_issue']?.toString().trim() ?? '';

  if (recommendedAction.isNotEmpty) {
    return recommendedAction;
  }
  if (spotifyMessage.isNotEmpty) {
    return spotifyMessage;
  }
  if (blockingIssue.isNotEmpty) {
    return 'Spotify playback could not continue because of: $blockingIssue.';
  }
  return defaultMessage;
}
