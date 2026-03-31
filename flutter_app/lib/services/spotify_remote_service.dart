import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'api_service.dart';

class SpotifyAppRemoteConfig {
  const SpotifyAppRemoteConfig({
    required this.clientId,
    required this.redirectUri,
  });

  final String clientId;
  final String redirectUri;
}

class SpotifyRemoteEvent {
  const SpotifyRemoteEvent(this.data);

  final Map<String, dynamic> data;

  String get type => data['type']?.toString().trim() ?? '';
}

class SpotifyRemoteException implements Exception {
  const SpotifyRemoteException(
    this.message, {
    this.code,
    this.details,
  });

  final String message;
  final String? code;
  final Object? details;

  Map<Object?, Object?>? get _detailMap =>
      details is Map ? Map<Object?, Object?>.from(details as Map) : null;

  String? _readString(String camelCaseKey, String snakeCaseKey) {
    final detailMap = _detailMap;
    final value = detailMap?[camelCaseKey] ?? detailMap?[snakeCaseKey];
    return value?.toString();
  }

  bool? _readBool(String camelCaseKey, String snakeCaseKey) {
    final detailMap = _detailMap;
    final value = detailMap?[camelCaseKey] ?? detailMap?[snakeCaseKey];
    return value is bool ? value : null;
  }

  String? get nativeErrorType {
    return _readString('nativeErrorType', 'native_error_type') ??
        details?.toString();
  }

  bool get requiresPlaybackApproval =>
      nativeErrorType == 'UserNotAuthorizedException';

  bool get requiresInteractiveAuthorization {
    return requiresPlaybackApproval ||
        nativeErrorType == 'PlaybackAuthorizationFailedException' ||
        nativeErrorType == 'PlaybackAuthorizationCancelledException' ||
        nativeErrorType == 'AuthenticationFailedException';
  }

  bool get mayNeedSpotifyWakeUp {
    return switch (nativeErrorType) {
      'SpotifyDisconnectedException' => true,
      'SpotifyConnectionTerminatedException' => true,
      'SpotifyRemoteServiceException' => true,
      'NotLoggedInException' => true,
      _ => code == 'connect_failed' || code == 'play_failed',
    };
  }

  bool? get authViewRequested =>
      _readBool('authViewRequested', 'auth_view_requested');

  bool? get authViewSurfaceDetected =>
      _readBool('authViewSurfaceDetected', 'auth_view_surface_detected');

  bool get authPromptWasSuppressed =>
      authViewRequested == true && authViewSurfaceDetected == false;

  String? get deviceManufacturer =>
      _readString('deviceManufacturer', 'device_manufacturer');

  String? get deviceModel => _readString('deviceModel', 'device_model');

  bool get isLikelyXiaomiDevice {
    final value =
        '${deviceManufacturer ?? ''} ${deviceModel ?? ''}'.toLowerCase();
    return value.contains('xiaomi') ||
        value.contains('redmi') ||
        value.contains('poco');
  }

  @override
  String toString() => message;
}

class SpotifyRemoteService {
  SpotifyRemoteService._();

  static final SpotifyRemoteService instance = SpotifyRemoteService._();
  static const MethodChannel _channel = MethodChannel('emotune/spotify_remote');
  static const EventChannel _eventChannel =
      EventChannel('emotune/spotify_remote_events');

  Future<SpotifyAppRemoteConfig>? _configFuture;
  Stream<SpotifyRemoteEvent>? _events;

  bool get isSupportedPlatform =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Stream<SpotifyRemoteEvent> get events {
    return _events ??= _eventChannel.receiveBroadcastStream().map((event) {
      if (event is Map) {
        return SpotifyRemoteEvent(
          Map<String, dynamic>.from(event as Map<Object?, Object?>),
        );
      }
      return const SpotifyRemoteEvent(<String, dynamic>{});
    });
  }

  Future<bool> isSpotifyAppInstalled() async {
    if (!isSupportedPlatform) {
      return false;
    }
    final installed = await _invoke<bool>('isSpotifyAppInstalled');
    return installed ?? false;
  }

  Future<void> ensureSpotifyInstalled() async {
    if (!isSupportedPlatform) {
      return;
    }
    final installed = await isSpotifyAppInstalled();
    if (!installed) {
      throw const SpotifyRemoteException(
        'Install the Spotify app on this phone, then return to EmoTune.',
        code: 'spotify_not_installed',
      );
    }
  }

  Future<bool> openSpotifyApp() async {
    final opened = await _invoke<bool>('openSpotifyApp');
    return opened ?? false;
  }

  Future<bool> connect({
    bool showAuthView = false,
    bool allowForegroundLaunch = true,
  }) async {
    final config = await _loadConfig();
    final connected = await _invoke<bool>('connect', {
      'clientId': config.clientId,
      'redirectUri': config.redirectUri,
      'showAuthView': showAuthView,
      'allowForegroundLaunch': allowForegroundLaunch,
    });
    return connected ?? false;
  }

  Future<bool> isConnected() async {
    final connected = await _invoke<bool>('isConnected');
    return connected ?? false;
  }

  Future<bool> disconnect() async {
    final disconnected = await _invoke<bool>('disconnect');
    return disconnected ?? false;
  }

  Future<bool> playUri(
    String uri, {
    bool showAuthView = false,
    bool allowForegroundLaunch = true,
  }) async {
    final config = await _loadConfig();
    final played = await _invoke<bool>('playUri', {
      'uri': uri,
      'clientId': config.clientId,
      'redirectUri': config.redirectUri,
      'showAuthView': showAuthView,
      'allowForegroundLaunch': allowForegroundLaunch,
    });
    return played ?? false;
  }

  Future<bool> pause() async {
    final paused = await _invoke<bool>('pause');
    return paused ?? false;
  }

  Future<bool> resume() async {
    final resumed = await _invoke<bool>('resume');
    return resumed ?? false;
  }

  Future<bool> togglePlayPause() async {
    final toggled = await _invoke<bool>('togglePlayPause');
    return toggled ?? false;
  }

  Future<bool> skipNext() async {
    final skipped = await _invoke<bool>('skipNext');
    return skipped ?? false;
  }

  Future<bool> skipPrevious() async {
    final skipped = await _invoke<bool>('skipPrevious');
    return skipped ?? false;
  }

  Future<bool> seekTo(int positionMs) async {
    final seeked = await _invoke<bool>('seekTo', {
      'positionMs': positionMs,
    });
    return seeked ?? false;
  }

  Future<bool> refreshPlayerState() async {
    final refreshed = await _invoke<bool>('refreshPlayerState');
    return refreshed ?? false;
  }

  Future<SpotifyAppRemoteConfig> _loadConfig() async {
    final cached = _configFuture;
    if (cached != null) {
      return cached;
    }

    final future = _fetchConfig();
    _configFuture = future;
    try {
      return await future;
    } catch (_) {
      _configFuture = null;
      rethrow;
    }
  }

  Future<SpotifyAppRemoteConfig> _fetchConfig() async {
    final payload = await ApiService.getSpotifyAppRemoteConfig();
    final clientId = payload['client_id']?.toString().trim() ?? '';
    final redirectUri = payload['redirect_uri']?.toString().trim() ?? '';

    if (clientId.isEmpty || redirectUri.isEmpty) {
      throw const SpotifyRemoteException(
        'Spotify App Remote is not configured on the backend yet.',
        code: 'spotify_remote_not_configured',
      );
    }

    return SpotifyAppRemoteConfig(
      clientId: clientId,
      redirectUri: redirectUri,
    );
  }

  Future<T?> _invoke<T>(String method, [Map<String, dynamic>? args]) async {
    if (!isSupportedPlatform) {
      throw const SpotifyRemoteException(
        'Spotify playback checks are only supported on Android in this build.',
      );
    }
    try {
      return await _channel.invokeMethod<T>(method, args);
    } on PlatformException catch (error) {
      throw SpotifyRemoteException(
        error.message ?? 'Spotify playback failed.',
        code: error.code,
        details: error.details,
      );
    }
  }
}
