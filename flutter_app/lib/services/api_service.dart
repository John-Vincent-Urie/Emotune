import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiException implements Exception {
  const ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ApiService {
  static const Duration _requestTimeout = Duration(seconds: 20);
  static const Duration _probeTimeout = Duration(seconds: 2);
  static const String _resolvedBaseUrlPrefsKey = 'resolved_api_base_url';
  static const String _configuredBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const List<String> _androidBaseUrlCandidates = [
    'http://127.0.0.1:8000/api',
    'http://10.0.2.2:8000/api',
  ];

  static String? _resolvedBaseUrl;
  static Future<String>? _resolvingBaseUrl;

  static String _defaultBaseUrl() {
    if (kIsWeb) {
      return 'http://127.0.0.1:8000/api';
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000/api';
    }
    return 'http://127.0.0.1:8000/api';
  }

  static Future<void> warmUp() async {
    try {
      await baseUrl;
    } catch (_) {}
  }

  static Future<String> get baseUrl async {
    if (_configuredBaseUrl.isNotEmpty) {
      return _configuredBaseUrl;
    }

    final cached = _resolvedBaseUrl;
    if (cached != null) {
      return cached;
    }

    final persisted = await _loadPersistedBaseUrl();
    if (persisted != null) {
      _resolvedBaseUrl = persisted;
      return persisted;
    }

    final inFlight = _resolvingBaseUrl;
    if (inFlight != null) {
      return inFlight;
    }

    final future = _resolveBaseUrl();
    _resolvingBaseUrl = future;
    try {
      final resolved = await future;
      await _cacheResolvedBaseUrl(resolved);
      return resolved;
    } finally {
      _resolvingBaseUrl = null;
    }
  }

  static Future<String> _resolveBaseUrl() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
      return _defaultBaseUrl();
    }

    for (final candidate in _androidBaseUrlCandidates) {
      if (await _canReachBaseUrl(candidate)) {
        return candidate;
      }
    }

    return _defaultBaseUrl();
  }

  static Future<String?> _loadPersistedBaseUrl() async {
    if (kIsWeb || _configuredBaseUrl.isNotEmpty) {
      return null;
    }
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_resolvedBaseUrlPrefsKey)?.trim();
    if (value == null || value.isEmpty) {
      return null;
    }
    return value;
  }

  static Future<void> _cacheResolvedBaseUrl(String baseUrl) async {
    _resolvedBaseUrl = baseUrl;
    if (kIsWeb || _configuredBaseUrl.isNotEmpty) {
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_resolvedBaseUrlPrefsKey, baseUrl);
  }

  static Future<bool> _canReachBaseUrl(String candidateBaseUrl) async {
    final probeUri = Uri.parse('$candidateBaseUrl/spotify/app-remote-config/');
    try {
      final response = await http.get(probeUri).timeout(_probeTimeout);
      return response.statusCode >= 200 && response.statusCode < 500;
    } on TimeoutException {
      return false;
    } on http.ClientException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static String _normalizePath(String path) {
    if (path.startsWith('/')) {
      return path;
    }
    return '/$path';
  }

  static String _backendUrl(String baseUrl) {
    return baseUrl.replaceFirst(RegExp(r'/api/?$'), '');
  }

  static String _formatBackendList(Iterable<String> baseUrls) {
    final backends = baseUrls
        .map(_backendUrl)
        .where((backend) => backend.isNotEmpty)
        .toSet()
        .toList();

    if (backends.isEmpty) {
      return 'the configured backend';
    }
    if (backends.length == 1) {
      return backends.first;
    }
    return backends.join(' or ');
  }

  static Future<Uri> _buildUri(
    String path, {
    String? baseUrlOverride,
    Map<String, String>? queryParameters,
  }) async {
    final resolvedBaseUrl = baseUrlOverride ?? await baseUrl;
    final uri = Uri.parse('$resolvedBaseUrl${_normalizePath(path)}');
    if (queryParameters == null || queryParameters.isEmpty) {
      return uri;
    }
    return uri.replace(
      queryParameters: {
        ...uri.queryParameters,
        ...queryParameters,
      },
    );
  }

  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('access_token');
  }

  static Future<Map<String, String>> authHeaders() async {
    final token = await getToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  static ApiException _networkError(
    Object error,
    Iterable<String> attemptedBaseUrls,
  ) {
    final backendTargets = _formatBackendList(attemptedBaseUrls);
    final guidance = StringBuffer(
      'Cannot reach the backend at $backendTargets. '
      'Make sure the Django server is running on port 8000.',
    );

    if (defaultTargetPlatform == TargetPlatform.android) {
      guidance.write(
        ' On the Android emulator use 10.0.2.2. '
        'On a physical phone use adb reverse tcp:8000 tcp:8000 '
        'or pass API_BASE_URL with your computer\'s LAN IP.',
      );
    }

    if (error is TimeoutException || error is http.ClientException) {
      return ApiException(guidance.toString());
    }

    return ApiException('Request failed: $error');
  }

  static Future<Map<String, dynamic>> _decodeObjectResponse(
    Future<http.Response> requestFuture,
  ) async {
    final response = await requestFuture;
    return _parseObject(response);
  }

  static Future<List<dynamic>> _decodeListResponse(
    Future<http.Response> requestFuture,
  ) async {
    final response = await requestFuture;
    final decoded = _parseJson(response);
    if (decoded is List<dynamic>) {
      return decoded;
    }
    throw const ApiException('Unexpected response from server.');
  }

  static Future<http.Response> _sendRequest(
    String path,
    Future<http.Response> Function(Uri uri) requestBuilder,
    {Map<String, String>? queryParameters}
  ) async {
    final normalizedPath = _normalizePath(path);
    final resolvedBaseUrl = await baseUrl;
    final uri = await _buildUri(
      normalizedPath,
      baseUrlOverride: resolvedBaseUrl,
      queryParameters: queryParameters,
    );

    try {
      return await requestBuilder(uri).timeout(_requestTimeout);
    } on TimeoutException catch (error) {
      return _retryAlternateAndroidBaseUrl(
        error,
        normalizedPath,
        resolvedBaseUrl,
        requestBuilder,
        queryParameters: queryParameters,
      );
    } on http.ClientException catch (error) {
      return _retryAlternateAndroidBaseUrl(
        error,
        normalizedPath,
        resolvedBaseUrl,
        requestBuilder,
        queryParameters: queryParameters,
      );
    }
  }

  static Future<http.Response> _retryAlternateAndroidBaseUrl(
    Object error,
    String normalizedPath,
    String attemptedBaseUrl,
    Future<http.Response> Function(Uri uri) requestBuilder,
    {Map<String, String>? queryParameters}
  ) async {
    final attemptedBaseUrls = <String>[attemptedBaseUrl];

    if (_configuredBaseUrl.isEmpty &&
        defaultTargetPlatform == TargetPlatform.android) {
      final fallbackBaseUrl = await _findAlternateAndroidBaseUrl(
        excluding: attemptedBaseUrl,
      );
      if (fallbackBaseUrl != null) {
        attemptedBaseUrls.add(fallbackBaseUrl);
        await _cacheResolvedBaseUrl(fallbackBaseUrl);
        final fallbackUri = await _buildUri(
          normalizedPath,
          baseUrlOverride: fallbackBaseUrl,
          queryParameters: queryParameters,
        );
        try {
          return await requestBuilder(fallbackUri).timeout(_requestTimeout);
        } on TimeoutException catch (fallbackError) {
          throw _networkError(fallbackError, attemptedBaseUrls);
        } on http.ClientException catch (fallbackError) {
          throw _networkError(fallbackError, attemptedBaseUrls);
        }
      }
    }

    throw _networkError(error, attemptedBaseUrls);
  }

  static Future<String?> _findAlternateAndroidBaseUrl({
    required String excluding,
  }) async {
    for (final candidate in _androidBaseUrlCandidates) {
      if (candidate == excluding) {
        continue;
      }
      if (await _canReachBaseUrl(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  static dynamic _parseJson(http.Response response) {
    dynamic decoded;
    try {
      decoded = response.body.isEmpty ? null : jsonDecode(response.body);
    } on FormatException {
      throw ApiException(
        'The server returned an invalid response (${response.statusCode}).',
      );
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }

    throw ApiException(_extractErrorMessage(decoded, response.statusCode));
  }

  static Map<String, dynamic> _parseObject(http.Response response) {
    final decoded = _parseJson(response);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    throw const ApiException('Unexpected response from server.');
  }

  static String _extractErrorMessage(dynamic decoded, int statusCode) {
    if (decoded is Map<String, dynamic>) {
      final error = decoded['error'];
      if (error is String && error.trim().isNotEmpty) {
        return error;
      }
      for (final value in decoded.values) {
        if (value is List && value.isNotEmpty) {
          return value.first.toString();
        }
        if (value != null && value.toString().trim().isNotEmpty) {
          return value.toString();
        }
      }
    }
    return 'Request failed with status $statusCode.';
  }

  static Future<void> _sendAndValidate(
    String path,
    Future<http.Response> Function(Uri uri) requestBuilder,
  ) async {
    final response = await _sendRequest(path, requestBuilder);
    _parseJson(response);
  }

  static Future<Map<String, dynamic>> register(
    String displayName,
    String email,
    String password, {
    required bool acceptTerms,
    bool personalizationOptIn = true,
  }) async {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/register/',
        (uri) => http.post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'username': displayName,
            'email': email,
            'password': password,
            'confirm_password': password,
            'accept_terms': acceptTerms,
            'personalization_opt_in': personalizationOptIn,
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> login(
    String email,
    String password,
  ) async {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/login/',
        (uri) => http.post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email, 'password': password}),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> getProfile() async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/users/profile/',
        (uri) => http.get(uri, headers: headers),
      ),
    );
  }

  static Future<Map<String, dynamic>> updateProfile(
    Map<String, dynamic> data,
  ) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/users/profile/',
        (uri) => http.patch(
          uri,
          headers: headers,
          body: jsonEncode(data),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> changePassword(
    String oldPass,
    String newPass,
  ) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/users/change-password/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'old_password': oldPass,
            'new_password': newPass,
            'confirm_new_password': newPass,
          }),
        ),
      ),
    );
  }

  static Map<String, dynamic> _recommendationOptionsPayload({
    String? outcomeMode,
    int? sessionLengthMinutes,
    int? checkInFrequencyTracks,
    Map<String, dynamic>? tasteProfile,
  }) {
    return {
      if (outcomeMode != null && outcomeMode.trim().isNotEmpty)
        'outcome_mode': outcomeMode.trim(),
      if (sessionLengthMinutes != null)
        'session_length_minutes': sessionLengthMinutes,
      if (checkInFrequencyTracks != null)
        'check_in_frequency_tracks': checkInFrequencyTracks,
      if (tasteProfile != null) 'taste_profile': tasteProfile,
    };
  }

  static Future<Map<String, dynamic>> analyzeEmotion(
    String text, {
    String? outcomeMode,
    int? sessionLengthMinutes,
    int? checkInFrequencyTracks,
    Map<String, dynamic>? tasteProfile,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/analyze/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'text': text,
            ..._recommendationOptionsPayload(
              outcomeMode: outcomeMode,
              sessionLengthMinutes: sessionLengthMinutes,
              checkInFrequencyTracks: checkInFrequencyTracks,
              tasteProfile: tasteProfile,
            ),
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> recommendByEmotion(
    String emotion, {
    String? text,
    String? outcomeMode,
    int? sessionLengthMinutes,
    int? checkInFrequencyTracks,
    Map<String, dynamic>? tasteProfile,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/recommend-by-emotion/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'emotion': emotion,
            if (text != null && text.trim().isNotEmpty) 'text': text.trim(),
            ..._recommendationOptionsPayload(
              outcomeMode: outcomeMode,
              sessionLengthMinutes: sessionLengthMinutes,
              checkInFrequencyTracks: checkInFrequencyTracks,
              tasteProfile: tasteProfile,
            ),
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> continueRecommendation(
    String continuationToken,
  ) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/recommendation-playlist/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'continuation_token': continuationToken,
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> checkFeelBetter(
    int historyId,
    int duration,
    int tracksPlayed,
  ) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/feel-better/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'history_id': historyId,
            'duration': duration,
            'tracks_played': tracksPlayed,
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> respondFeelBetter({
    required int historyId,
    required bool feltBetter,
    required int duration,
    required int tracksPlayed,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/feel-better-response/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'history_id': historyId,
            'felt_better': feltBetter,
            'duration': duration,
            'tracks_played': tracksPlayed,
          }),
        ),
      ),
    );
  }

  static Future<List<dynamic>> getFavorites() async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/users/favorites/',
        (uri) => http.get(uri, headers: headers),
      ),
    );
  }

  static Future<void> addFavorite(Map<String, dynamic> track) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/favorites/',
      (uri) => http.post(
        uri,
        headers: headers,
        body: jsonEncode(track),
      ),
    );
  }

  static Future<void> removeFavorite(String trackId) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/favorites/$trackId/',
      (uri) => http.delete(
        uri,
        headers: headers,
      ),
    );
  }

  static Future<List<dynamic>> getHistory() async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/users/history/',
        (uri) => http.get(uri, headers: headers),
      ),
    );
  }

  static Future<List<dynamic>> getEmotionStats() async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/users/emotion-stats/',
        (uri) => http.get(uri, headers: headers),
      ),
    );
  }

  static Future<List<dynamic>> searchArtists(String query) async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/spotify/search-artists/',
        (uri) => http.get(uri, headers: headers),
        queryParameters: {'q': query},
      ),
    );
  }

  static Future<void> updateArtists(List<String> artists) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/update-artists/',
      (uri) => http.put(
        uri,
        headers: headers,
        body: jsonEncode({'preferred_artists': artists}),
      ),
    );
  }

  static Future<void> updateListenTime(
    String trackId,
    String emotion,
    int duration,
    String trackName,
    String artistName, {
    String itemType = 'track',
    int? historyId,
    bool trainSession = true,
  }) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/listen-time/',
      (uri) => http.post(
        uri,
        headers: headers,
        body: jsonEncode({
          'track_id': trackId,
          'emotion': emotion,
          'duration': duration,
          'track_name': trackName,
          'artist_name': artistName,
          'item_type': itemType,
          if (historyId != null) 'history_id': historyId,
          'train_session': trainSession,
        }),
      ),
    );
  }

  static Future<Map<String, dynamic>> getSpotifyAppRemoteConfig() async {
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/app-remote-config/',
        (uri) => http.get(uri),
      ),
    );
  }

  static Future<Map<String, dynamic>> getSpotifyPlaybackDebugStatus() async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/debug-status/',
        (uri) => http.get(uri, headers: headers),
      ),
    );
  }

  static Future<Map<String, dynamic>> prepareSpotifyPlayback({
    String? deviceId,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/prepare-playback/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            if (deviceId != null && deviceId.trim().isNotEmpty)
              'device_id': deviceId.trim(),
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> controlSpotifyPlayback({
    required String action,
    String? uri,
    String? deviceId,
    int? positionMs,
    bool? shuffleEnabled,
    String? repeatMode,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/player-control/',
        (uriObject) => http.post(
          uriObject,
          headers: headers,
          body: jsonEncode({
            'action': action,
            if (uri != null && uri.trim().isNotEmpty) 'uri': uri.trim(),
            if (deviceId != null && deviceId.trim().isNotEmpty)
              'device_id': deviceId.trim(),
            if (positionMs != null) 'position_ms': positionMs,
            if (shuffleEnabled != null) 'shuffle_enabled': shuffleEnabled,
            if (repeatMode != null && repeatMode.trim().isNotEmpty)
              'repeat_mode': repeatMode.trim(),
          }),
        ),
      ),
    );
  }

  static Future<Map<String, dynamic>> disconnectSpotify() async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/disconnect/',
        (uri) => http.post(
          uri,
          headers: headers,
          body: jsonEncode(const <String, dynamic>{}),
        ),
      ),
    );
  }

  static Future<String> getSpotifyAuthUrl(String userId) async {
    final data = await _decodeObjectResponse(
      _sendRequest(
        '/spotify/auth-url/',
        (uri) => http.get(uri),
        queryParameters: {'user_id': userId},
      ),
    );
    return data['auth_url'];
  }
}
