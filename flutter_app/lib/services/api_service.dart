import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;

  /// The HTTP status when the server answered, null when it was never
  /// reached. Lets callers tell "signed out" (401) from "backend down".
  final int? statusCode;

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

  /// Every API call goes through this client, which stamps the current access
  /// token onto any request that asked for one. Call sites capture their
  /// headers before sending, so without it a replay after a token refresh
  /// would resend the expired token.
  static http.Client _http = _FreshTokenClient(http.Client());

  @visibleForTesting
  static set httpClient(http.Client client) {
    _http = _FreshTokenClient(client);
  }

  /// Called once the session cannot be renewed and the tokens have been
  /// cleared. main.dart uses it to reset auth state and go to login.
  static Future<void> Function()? onSessionExpired;

  /// The refresh on the wire, shared by every request that 401s while it
  /// runs. Rotation blacklists a refresh token on first use, so two parallel
  /// refreshes would have the second one fail and sign the user out.
  static Future<bool>? _refreshInFlight;

  /// Endpoints whose 401 is an answer, not an expired token. Refreshing on
  /// them could loop (the refresh endpoint) or mask bad credentials (login).
  static const Set<String> _noRefreshPaths = {
    '/users/token/refresh/',
    '/users/login/',
    '/users/register/',
    '/users/logout/',
  };

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

    // The setup guidance is for developers; end users get plain words.
    debugPrint('[ApiService] $guidance ($error)');
    return const ApiException(
      "Can't connect to EmoTune right now. Check your internet connection "
      'and try again.',
    );
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

  /// Sends the request, and on a 401 for an authenticated call renews the
  /// access token (one shared refresh) and replays it once.
  static Future<http.Response> _sendRequest(
    String path,
    Future<http.Response> Function(Uri uri) requestBuilder,
    {Map<String, String>? queryParameters}
  ) async {
    final response = await _sendOnce(
      path,
      requestBuilder,
      queryParameters: queryParameters,
    );
    if (response.statusCode != 401 ||
        _noRefreshPaths.contains(_normalizePath(path))) {
      return response;
    }
    final sentAuthorization = response.request?.headers['Authorization'];
    if (sentAuthorization == null) {
      return response;
    }
    if (!await _renewAccessToken(sentAuthorization)) {
      return response;
    }
    return _sendOnce(path, requestBuilder, queryParameters: queryParameters);
  }

  static Future<bool> _renewAccessToken(String sentAuthorization) async {
    final current = await getToken();
    if (current == null) {
      // Signed out while this request was in flight; nothing to renew.
      return false;
    }
    if ('Bearer $current' != sentAuthorization) {
      // Another request already renewed the token after this one went out.
      return true;
    }
    return _refreshInFlight ??=
        _refreshTokens().whenComplete(() => _refreshInFlight = null);
  }

  static Future<bool> _refreshTokens() async {
    final prefs = await SharedPreferences.getInstance();
    final refresh = prefs.getString('refresh_token') ?? '';
    if (refresh.isNotEmpty) {
      try {
        final tokens = await refreshToken(refresh);
        final access = tokens['access']?.toString() ?? '';
        if (access.isNotEmpty) {
          await prefs.setString('access_token', access);
          final rotated = tokens['refresh']?.toString() ?? '';
          if (rotated.isNotEmpty) {
            await prefs.setString('refresh_token', rotated);
          }
          return true;
        }
      } on ApiException catch (error) {
        // Backend unreachable or erroring says nothing about the session:
        // keep the tokens and let this request fail as it did.
        final status = error.statusCode;
        if (status == null || status >= 500) {
          return false;
        }
      }
    }
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
    await onSessionExpired?.call();
    return false;
  }

  static Future<http.Response> _sendOnce(
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

    throw ApiException(
      _extractErrorMessage(decoded, response.statusCode),
      statusCode: response.statusCode,
    );
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
        return _asSentence(error);
      }
      for (final value in decoded.values) {
        if (value is List && value.isNotEmpty) {
          return _asSentence(value.first.toString());
        }
        if (value != null && value.toString().trim().isNotEmpty) {
          return _asSentence(value.toString());
        }
      }
    }
    return 'Request failed with status $statusCode.';
  }

  /// Django's built-in validators answer in lowercase ("user with this email
  /// already exists."); shown as-is they read like a log line.
  static String _asSentence(String message) {
    final trimmed = message.trim();
    if (trimmed.isEmpty) return trimmed;
    return trimmed[0].toUpperCase() + trimmed.substring(1);
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
        (uri) => _http.post(
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
        (uri) => _http.post(
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
        (uri) => _http.get(uri, headers: headers),
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
        (uri) => _http.patch(
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
        (uri) => _http.post(
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

  /// Ask the server to email a one-time code to [email].
  ///
  /// Succeeds whether or not an account owns the address -- the server will not
  /// say which, so the app must not imply it either.
  static Future<Map<String, dynamic>> requestPasswordReset(String email) async {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/password-reset/',
        (uri) => _http.post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email}),
        ),
      ),
    );
  }

  /// Check a reset code without spending it, so the app can move the user on
  /// to choosing a password only once the code is known to be good.
  static Future<Map<String, dynamic>> verifyPasswordResetCode(
    String email,
    String code,
  ) async {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/password-reset/verify/',
        (uri) => _http.post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email, 'code': code}),
        ),
      ),
    );
  }

  /// Spend the code and set the new password.
  static Future<Map<String, dynamic>> confirmPasswordReset(
    String email,
    String code,
    String newPassword,
  ) async {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/password-reset/confirm/',
        (uri) => _http.post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'email': email,
            'code': code,
            'new_password': newPassword,
            'confirm_new_password': newPassword,
          }),
        ),
      ),
    );
  }

  /// Options the app still chooses.
  ///
  /// `outcome_mode` and `check_in_frequency_tracks` are deliberately absent:
  /// the backend routes the mode from the detected emotion (docs/arch) and
  /// takes the check-in cadence from that mode's default, so sending either
  /// from here would only let a stale client override the routing.
  static Map<String, dynamic> _recommendationOptionsPayload({
    int? sessionLengthMinutes,
    Map<String, dynamic>? tasteProfile,
  }) {
    return {
      if (sessionLengthMinutes != null)
        'session_length_minutes': sessionLengthMinutes,
      if (tasteProfile != null) 'taste_profile': tasteProfile,
    };
  }

  static Future<Map<String, dynamic>> analyzeEmotion(
    String text, {
    int? sessionLengthMinutes,
    Map<String, dynamic>? tasteProfile,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/analyze/',
        (uri) => _http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'text': text,
            ..._recommendationOptionsPayload(
              sessionLengthMinutes: sessionLengthMinutes,
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
    int? sessionLengthMinutes,
    Map<String, dynamic>? tasteProfile,
  }) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/recommend-by-emotion/',
        (uri) => _http.post(
          uri,
          headers: headers,
          body: jsonEncode({
            'emotion': emotion,
            if (text != null && text.trim().isNotEmpty) 'text': text.trim(),
            ..._recommendationOptionsPayload(
              sessionLengthMinutes: sessionLengthMinutes,
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
        (uri) => _http.post(
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
        (uri) => _http.post(
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
        (uri) => _http.post(
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

  /// Verified hotlines and counselors. Public endpoint, but the token is sent
  /// when present so the request looks like every other one.
  static Future<Map<String, dynamic>> getSupportResources() async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest('/support-resources/', (uri) => _http.get(uri, headers: headers)),
    );
  }

  static Future<List<dynamic>> getFavorites() async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/users/favorites/',
        (uri) => _http.get(uri, headers: headers),
      ),
    );
  }

  /// Returns the saved favorite record, which carries the server's id,
  /// `added_at` and emotion tag.
  static Future<Map<String, dynamic>> addFavorite(
    Map<String, dynamic> track,
  ) async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/users/favorites/',
        (uri) => _http.post(
          uri,
          headers: headers,
          body: jsonEncode(track),
        ),
      ),
    );
  }

  static Future<void> removeFavorite(String trackId) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/favorites/$trackId/',
      (uri) => _http.delete(
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
        (uri) => _http.get(uri, headers: headers),
      ),
    );
  }

  static Future<List<dynamic>> getEmotionStats() async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/users/emotion-stats/',
        (uri) => _http.get(uri, headers: headers),
      ),
    );
  }

  static Future<List<dynamic>> searchArtists(String query) async {
    final headers = await authHeaders();
    return _decodeListResponse(
      _sendRequest(
        '/spotify/search-artists/',
        (uri) => _http.get(uri, headers: headers),
        queryParameters: {'q': query},
      ),
    );
  }

  static Future<void> updateArtists(List<String> artists) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/update-artists/',
      (uri) => _http.put(
        uri,
        headers: headers,
        body: jsonEncode({'preferred_artists': artists}),
      ),
    );
  }

  /// Report a finished playback.
  ///
  /// [durationMs] is the track's full length, which lets the backend judge a
  /// listen against the track rather than a flat number of seconds.
  /// [endedReason] is 'completed' or 'skipped'; skips are what give the music
  /// picker's ranker something to learn against.
  static Future<void> updateListenTime(
    String trackId,
    String emotion,
    int duration,
    String trackName,
    String artistName, {
    String itemType = 'track',
    int? historyId,
    bool trainSession = true,
    int? durationMs,
    String endedReason = 'skipped',
  }) async {
    final headers = await authHeaders();
    await _sendAndValidate(
      '/users/listen-time/',
      (uri) => _http.post(
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
          if (durationMs != null) 'duration_ms': durationMs,
          'ended_reason': endedReason,
        }),
      ),
    );
  }

  static Future<Map<String, dynamic>> getSpotifyAppRemoteConfig() async {
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/app-remote-config/',
        (uri) => _http.get(uri),
      ),
    );
  }

  static Future<Map<String, dynamic>> getSpotifyPlaybackDebugStatus() async {
    final headers = await authHeaders();
    return _decodeObjectResponse(
      _sendRequest(
        '/spotify/debug-status/',
        (uri) => _http.get(uri, headers: headers),
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
        (uri) => _http.post(
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
        (uriObject) => _http.post(
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
        (uri) => _http.post(
          uri,
          headers: headers,
          body: jsonEncode(const <String, dynamic>{}),
        ),
      ),
    );
  }

  /// Revokes the refresh token server-side. Clearing tokens on the device only
  /// hides them; the refresh token stays usable for weeks until it is
  /// blacklisted, so sign-out has to tell the backend.
  static Future<void> logout(String refreshToken) async {
    await _sendRequest(
      '/users/logout/',
      (uri) => _http.post(
        uri,
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh': refreshToken}),
      ),
    );
  }

  /// Trades the refresh token for a fresh access token. Rotation is on in the
  /// backend, so the response usually carries a new refresh token as well and
  /// the old one is blacklisted; the caller must store both.
  static Future<Map<String, dynamic>> refreshToken(String refreshToken) {
    return _decodeObjectResponse(
      _sendRequest(
        '/users/token/refresh/',
        (uri) => _http.post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh': refreshToken}),
        ),
      ),
    );
  }

  /// Asks the backend for a Spotify login URL. The account to link comes from
  /// the access token, so this call has to be authenticated and no longer
  /// passes a user id the caller could point at somebody else.
  static Future<String> getSpotifyAuthUrl() async {
    final headers = await authHeaders();
    final data = await _decodeObjectResponse(
      _sendRequest(
        '/spotify/auth-url/',
        (uri) => _http.get(uri, headers: headers),
      ),
    );
    return data['auth_url'];
  }
}

/// Overwrites the Authorization header with the token stored right now, so a
/// request replayed after a refresh carries the new token. Requests sent
/// without the header (login, register, refresh) are left alone.
class _FreshTokenClient extends http.BaseClient {
  _FreshTokenClient(this._inner);

  final http.Client _inner;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request.headers.containsKey('Authorization')) {
      final token = await ApiService.getToken();
      if (token != null) {
        request.headers['Authorization'] = 'Bearer $token';
      }
    }
    final response = await _inner.send(request);
    if (response.request != null) {
      return response;
    }
    // The 401 retry reads the token a request was sent with off
    // response.request; not every client fills it in, so make sure it is.
    return http.StreamedResponse(
      response.stream,
      response.statusCode,
      contentLength: response.contentLength,
      request: request,
      headers: response.headers,
      isRedirect: response.isRedirect,
      persistentConnection: response.persistentConnection,
      reasonPhrase: response.reasonPhrase,
    );
  }

  @override
  void close() => _inner.close();
}
