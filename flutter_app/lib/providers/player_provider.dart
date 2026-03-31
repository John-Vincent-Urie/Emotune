import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import '../services/api_service.dart';
import '../services/spotify_remote_service.dart';

class PlayerProvider extends ChangeNotifier {
  final AudioPlayer _player = AudioPlayer();
  final SpotifyRemoteService _spotifyRemote = SpotifyRemoteService.instance;
  final math.Random _random = math.Random();
  static const int _spotifyStateRefreshIntervalSeconds = 4;
  static const Duration _remoteWarmupTimeout = Duration(seconds: 2);
  static const Duration _preparedPreviewSeekTimeout =
      Duration(milliseconds: 140);

  StreamSubscription<SpotifyRemoteEvent>? _spotifyRemoteEventsSubscription;
  Timer? _remotePlaybackProgressTimer;
  Map<String, dynamic>? _currentTrack;
  Map<String, dynamic>? _currentContext;
  List<Map<String, dynamic>> _playlist = [];
  List<Map<String, dynamic>> _contextQueue = [];
  final Set<String> _favoriteTrackIds = <String>{};
  int _currentIndex = 0;
  bool _isPlaying = false;
  bool _isLoading = false;
  bool _isUsingSpotifyRemote = false;
  bool _isUsingSpotifyAppRemote = false;
  bool _isRefreshingSpotifyState = false;
  bool _favoritesLoaded = false;
  bool _favoritesBusy = false;
  bool _shuffleEnabled = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  Duration? _dragPreviewPosition;
  String? _currentEmotion;
  int? _historyId;
  int _totalListenTime = 0;
  bool _feelBetterPromptOpen = false;
  int _completedTrackCount = 0;
  int? _nextFeelBetterCheckpoint = 5;
  Map<String, dynamic>? _sessionPlan;
  Map<String, dynamic> _tasteProfile = <String, dynamic>{
    'familiarity': 'balanced',
    'prefer_instrumental': false,
    'train_session': true,
  };
  String _outcomeMode = 'match_mood';
  String? _outcomeLabel;
  String? _outcomeDescription;
  bool _trainOnThisSession = true;
  String? _errorMessage;
  String? _playbackStatusCode;
  String? _playbackStatusDetail;
  String _repeatMode = 'off';
  int _spotifyStateTickCount = 0;
  ConcatenatingAudioSource? _previewQueueSource;
  Future<void>? _previewQueueReady;
  List<int?> _previewSourceIndexByPlaylistIndex = <int?>[];
  int _previewQueueVersion = 0;
  bool _isAdvancingTrack = false;
  bool _isWarmingSpotifyPlayback = false;
  bool _isSeekInProgress = false;

  Map<String, dynamic>? get currentTrack => _currentTrack;
  Map<String, dynamic>? get currentContext => _currentContext;
  List<Map<String, dynamic>> get playlist => _playlist;
  List<Map<String, dynamic>> get contextQueue => _contextQueue;
  List<Map<String, dynamic>> get activeQueue => _contextQueue.isNotEmpty
      ? _contextQueue
      : (_shouldSurfaceResolvedRemoteTrack
          ? [normalizeTrack(_currentTrack!)]
          : _playlist);
  bool get isPlaying => _isPlaying;
  bool get isLoading => _isLoading;
  bool get isUsingSpotifyRemote => _isUsingSpotifyRemote;
  Duration get position => _position;
  Duration get displayPosition => _dragPreviewPosition ?? _position;
  Duration get duration => _duration;
  int get currentIndex => _currentIndex;
  String? get currentEmotion => _currentEmotion;
  int? get historyId => _historyId;
  Map<String, dynamic>? get sessionPlan => _sessionPlan;
  Map<String, dynamic> get tasteProfile => _tasteProfile;
  String get outcomeMode => _outcomeMode;
  String? get outcomeLabel => _outcomeLabel;
  String? get outcomeDescription => _outcomeDescription;
  bool get trainOnThisSession => _trainOnThisSession;
  String get familiarity =>
      _tasteProfile['familiarity']?.toString() ?? 'balanced';
  bool get preferInstrumental => _tasteProfile['prefer_instrumental'] == true;
  bool get hasActiveSessionPlan => _sessionPlan?['enabled'] == true;
  bool get hasRecommendationContext =>
      hasActiveSessionPlan ||
      _outcomeMode != 'match_mood' ||
      familiarity != 'balanced' ||
      preferInstrumental ||
      !_trainOnThisSession;
  bool get isSessionComplete => _sessionPlan?['completed'] == true;
  Duration get sessionProgressDuration =>
      Duration(seconds: _safeInt(_sessionPlan?['progress_seconds']));
  Duration get sessionTargetDuration =>
      Duration(seconds: _safeInt(_sessionPlan?['target_seconds']));
  double get sessionProgressFraction {
    final targetSeconds = sessionTargetDuration.inSeconds;
    if (targetSeconds <= 0) {
      return 0.0;
    }
    return (sessionProgressDuration.inSeconds / targetSeconds).clamp(0.0, 1.0);
  }

  int? get sessionNextCheckInTrack => _checkpointFromSessionPlan(_sessionPlan);
  String get sessionPhase => _sessionPlan?['phase']?.toString().trim() ?? '';
  String? get errorMessage => _errorMessage;
  bool get isShuffleEnabled => _shuffleEnabled;
  String get repeatMode => _repeatMode;
  bool get isRepeatEnabled => _repeatMode != 'off';
  bool get isRepeatQueueMode => _repeatMode == 'context';
  bool get isRepeatTrackMode => _repeatMode == 'track';
  bool get isCurrentTrackFavorite => isFavoriteTrack(_currentTrack);
  String? get playbackStatusCode => _playbackStatusCode;
  String get playbackStatusLabel {
    switch (_playbackStatusCode) {
      case 'spotify_background':
        return 'Full Spotify track playing in background';
      case 'spotify_queue_loading':
        return 'Loading Spotify queue in background';
      case 'preview_local':
        return '30-second preview playing locally';
      case 'spotify_background_unavailable':
        return 'Spotify background device unavailable';
      case 'not_directly_playable':
        return 'This item is not directly playable here';
      case 'preview_error':
        return 'Preview playback failed';
      default:
        return _isUsingSpotifyRemote
            ? 'Spotify background playback'
            : 'Playback ready';
    }
  }

  String? get playbackStatusDetail => _playbackStatusDetail;
  String get playbackStatusShortLabel {
    switch (_playbackStatusCode) {
      case 'spotify_background':
        return 'Spotify background';
      case 'spotify_queue_loading':
        return 'Loading queue';
      case 'preview_local':
        return 'Local preview';
      case 'spotify_background_unavailable':
        return 'Spotify unavailable';
      case 'not_directly_playable':
        return 'Not playable here';
      case 'preview_error':
        return 'Preview failed';
      default:
        return _isUsingSpotifyRemote ? 'Spotify' : 'Playback';
    }
  }

  bool get isShowingCurrentRemoteTrackOnly => _shouldSurfaceResolvedRemoteTrack;
  bool get isResolvingContextQueue =>
      _isUsingSpotifyRemote &&
      _contextQueue.isEmpty &&
      ((_currentTrack == null &&
              (_currentContext?['uri']?.toString().isNotEmpty ?? false)) ||
          (_currentTrack != null && _isContainerItem(_currentTrack!)));

  static const Set<String> _supportedSpotifyItemTypes = {
    'track',
    'playlist',
    'album',
    'artist',
    'episode',
    'show',
  };

  static Map<String, dynamic> normalizeTrack(Map<String, dynamic> rawTrack) {
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
          _supportedSpotifyItemTypes.contains(parsedType)) {
        itemType = itemType.isNotEmpty ? itemType : parsedType;
        itemId = itemId.isNotEmpty ? itemId : segments[1];
      }
    }

    if (uri.isEmpty &&
        itemId.isNotEmpty &&
        (itemType.isEmpty || _supportedSpotifyItemTypes.contains(itemType))) {
      final resolvedType = itemType.isNotEmpty ? itemType : 'track';
      uri = 'spotify:$resolvedType:$itemId';
    }

    if (spotifyUrl.isEmpty &&
        itemId.isNotEmpty &&
        (itemType.isEmpty || _supportedSpotifyItemTypes.contains(itemType))) {
      final resolvedType = itemType.isNotEmpty ? itemType : 'track';
      spotifyUrl = 'https://open.spotify.com/$resolvedType/$itemId';
    }

    track['id'] = itemId.isNotEmpty ? itemId : (uri.isNotEmpty ? uri : rawId);
    track['item_type'] = itemType.isNotEmpty ? itemType : 'track';
    track['uri'] = uri;
    track['spotify_url'] = spotifyUrl;
    return track;
  }

  static bool _isContainerType(String itemType) {
    return {'playlist', 'album', 'artist', 'show', 'collection'}
        .contains(itemType.trim().toLowerCase());
  }

  static bool _isContainerItem(Map<String, dynamic> track) {
    final itemType = track['item_type']?.toString() ?? '';
    return _isContainerType(itemType);
  }

  static List<Map<String, dynamic>> normalizeTrackList(
      List<dynamic> rawTracks) {
    return rawTracks
        .whereType<Map>()
        .map((track) => normalizeTrack(Map<String, dynamic>.from(track)))
        .where((track) {
      final uri = track['uri']?.toString().trim() ?? '';
      final previewUrl = track['preview_url']?.toString().trim() ?? '';
      return uri.isNotEmpty || previewUrl.isNotEmpty;
    }).toList();
  }

  static int _safeInt(Object? value, [int defaultValue = 0]) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value?.toString() ?? '') ?? defaultValue;
  }

  static Map<String, dynamic>? _normalizeObjectMap(dynamic value) {
    if (value is! Map) {
      return null;
    }
    return Map<String, dynamic>.from(value);
  }

  static String _normalizeOutcomeMode(String? value) {
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

  static Map<String, dynamic> _normalizeTasteProfile(
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

  void _applyRecommendationContext({
    Map<String, dynamic>? sessionPlan,
    Map<String, dynamic>? tasteProfile,
    String? outcomeMode,
    String? outcomeLabel,
    String? outcomeDescription,
    bool? trainOnThisSession,
  }) {
    _sessionPlan = _normalizeObjectMap(sessionPlan);
    _tasteProfile = _normalizeTasteProfile(
      tasteProfile,
      trainOnThisSession: trainOnThisSession,
    );
    _trainOnThisSession = _tasteProfile['train_session'] != false;
    _outcomeMode = _normalizeOutcomeMode(outcomeMode);
    _outcomeLabel = outcomeLabel?.trim().isNotEmpty == true
        ? outcomeLabel!.trim()
        : _sessionPlan?['label']?.toString().trim();
    _outcomeDescription = outcomeDescription?.trim().isNotEmpty == true
        ? outcomeDescription!.trim()
        : _sessionPlan?['description']?.toString().trim();
  }

  void _applyResponseSessionContext(Map<String, dynamic> result) {
    final responseSessionPlan = _normalizeObjectMap(result['session_plan']);
    if (responseSessionPlan != null) {
      _sessionPlan = responseSessionPlan;
    }
    _nextFeelBetterCheckpoint = _checkpointFromResponse(result) ??
        _checkpointFromSessionPlan(_sessionPlan);
  }

  void _updateLocalSessionPlanProgress() {
    if (_sessionPlan == null) {
      return;
    }

    final updated = Map<String, dynamic>.from(_sessionPlan!);
    updated['progress_seconds'] = math.max(_totalListenTime, 0);
    updated['tracks_played'] = math.max(_completedTrackCount, 0);

    final targetSeconds = _safeInt(updated['target_seconds']);
    final phaseCutoffSeconds =
        math.max(_safeInt(updated['phase_cutoff_minutes']) * 60, 60);
    if (targetSeconds > 0 && _totalListenTime >= targetSeconds) {
      updated['phase'] = 'close';
    } else if (_totalListenTime >= phaseCutoffSeconds) {
      updated['phase'] = 'support';
    } else {
      updated['phase'] = 'settle';
    }

    if (updated['completed'] == true) {
      updated['next_check_in_tracks'] = null;
    }

    _sessionPlan = updated;
  }

  static String _trackIdentity(Map<String, dynamic> rawTrack) {
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

  static List<Map<String, dynamic>> mergeTrackLists(
    List<dynamic> currentTracks,
    List<dynamic> incomingTracks,
  ) {
    final merged = <Map<String, dynamic>>[];
    final seenKeys = <String>{};

    void appendAll(List<dynamic> tracks) {
      for (final rawTrack in tracks.whereType<Map>()) {
        final normalizedTrack =
            normalizeTrack(Map<String, dynamic>.from(rawTrack));
        final identity = _trackIdentity(normalizedTrack);
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

  PlayerProvider() {
    _player.positionStream.listen((position) {
      if (_isUsingSpotifyRemote ||
          _dragPreviewPosition != null ||
          _isSeekInProgress) {
        return;
      }
      _position = position;
      notifyListeners();
    });
    _player.durationStream.listen((duration) {
      if (_isUsingSpotifyRemote) {
        return;
      }
      if (duration != null) {
        _duration = duration;
        notifyListeners();
      }
    });
    _player.playerStateStream.listen((state) {
      if (_isUsingSpotifyRemote) {
        return;
      }
      _isPlaying = state.playing;
      if (state.processingState == ProcessingState.completed) {
        _onTrackCompleted();
      }
      notifyListeners();
    });
    _remotePlaybackProgressTimer = Timer.periodic(
      const Duration(seconds: 1),
      (_) {
        _tickRemotePlaybackProgress();
        _scheduleSpotifyPlaybackStateRefresh();
      },
    );
    if (_spotifyRemote.isSupportedPlatform) {
      _spotifyRemoteEventsSubscription = _spotifyRemote.events.listen(
        _handleSpotifyRemoteEvent,
        onError: (Object error, StackTrace stackTrace) {
          debugPrint('[SpotifyAppRemote][events_failed] $error');
        },
      );
    }
    unawaited(refreshFavorites());
  }

  void loadPlaylist(
    List<Map<String, dynamic>> tracks,
    String emotion, {
    int? historyId,
    bool autoplay = true,
    Map<String, dynamic>? sessionPlan,
    Map<String, dynamic>? tasteProfile,
    String? outcomeMode,
    String? outcomeLabel,
    String? outcomeDescription,
    bool? trainOnThisSession,
  }) {
    _playlist = normalizeTrackList(tracks);
    _contextQueue = [];
    _currentContext = null;
    _currentEmotion = emotion;
    _historyId = historyId;
    _applyRecommendationContext(
      sessionPlan: sessionPlan,
      tasteProfile: tasteProfile,
      outcomeMode: outcomeMode,
      outcomeLabel: outcomeLabel,
      outcomeDescription: outcomeDescription,
      trainOnThisSession: trainOnThisSession,
    );
    _totalListenTime = _safeInt(_sessionPlan?['progress_seconds']);
    _completedTrackCount = _safeInt(_sessionPlan?['tracks_played']);
    _nextFeelBetterCheckpoint = _checkpointFromSessionPlan(_sessionPlan) ??
        (historyId != null ? 5 : null);
    _feelBetterPromptOpen = false;
    _errorMessage = null;
    _playbackStatusCode = null;
    _playbackStatusDetail = null;
    _dragPreviewPosition = null;
    _shuffleEnabled = false;
    _repeatMode = 'off';
    _isUsingSpotifyAppRemote = false;
    _isAdvancingTrack = false;
    _configurePreviewQueueForPlaylist(_playlist);
    if (_playlist.isNotEmpty) {
      unawaited(_warmSpotifyPlaybackForTrack(_playlist.first));
    }
    unawaited(refreshFavorites());
    if (_playlist.isNotEmpty && autoplay) {
      unawaited(playTrackAtIndex(0, preferInstantPreview: true));
    } else {
      notifyListeners();
    }
  }

  void mergePlaylistTracks(
    List<Map<String, dynamic>> tracks, {
    String? emotion,
    int? historyId,
    Map<String, dynamic>? sessionPlan,
    Map<String, dynamic>? tasteProfile,
    String? outcomeMode,
    String? outcomeLabel,
    String? outcomeDescription,
    bool? trainOnThisSession,
  }) {
    final previousPlaylistLength = _playlist.length;
    final mergedPlaylist = mergeTrackLists(_playlist, tracks);
    if (mergedPlaylist.isEmpty) {
      if (emotion != null && emotion.trim().isNotEmpty) {
        _currentEmotion = emotion.trim();
      }
      if (historyId != null) {
        _historyId = historyId;
      }
      _applyRecommendationContext(
        sessionPlan: sessionPlan,
        tasteProfile: tasteProfile,
        outcomeMode: outcomeMode,
        outcomeLabel: outcomeLabel,
        outcomeDescription: outcomeDescription,
        trainOnThisSession: trainOnThisSession,
      );
      _nextFeelBetterCheckpoint =
          _checkpointFromSessionPlan(_sessionPlan) ?? _nextFeelBetterCheckpoint;
      notifyListeners();
      return;
    }

    _playlist = mergedPlaylist;
    if (emotion != null && emotion.trim().isNotEmpty) {
      _currentEmotion = emotion.trim();
    }
    if (historyId != null) {
      _historyId = historyId;
    }
    _applyRecommendationContext(
      sessionPlan: sessionPlan,
      tasteProfile: tasteProfile,
      outcomeMode: outcomeMode,
      outcomeLabel: outcomeLabel,
      outcomeDescription: outcomeDescription,
      trainOnThisSession: trainOnThisSession,
    );
    _nextFeelBetterCheckpoint =
        _checkpointFromSessionPlan(_sessionPlan) ?? _nextFeelBetterCheckpoint;

    if (_currentTrack != null) {
      final currentIdentity = _trackIdentity(_currentTrack!);
      final matchedIndex = _playlist.indexWhere(
        (track) => _trackIdentity(track) == currentIdentity,
      );
      if (matchedIndex >= 0) {
        _currentIndex = matchedIndex;
        _playlist[matchedIndex] = {
          ..._playlist[matchedIndex],
          ...normalizeTrack(_currentTrack!),
        };
      } else if (_currentIndex >= _playlist.length) {
        _currentIndex = _playlist.length - 1;
      }
    }

    _extendPreviewQueueForMergedPlaylist(
      previousPlaylistLength: previousPlaylistLength,
      mergedPlaylist: _playlist,
    );

    notifyListeners();
  }

  Future<void> playTrackAtIndex(
    int index, {
    bool preferInstantPreview = false,
  }) async {
    if (index < 0 || index >= _playlist.length) {
      return;
    }

    final track = normalizeTrack(_playlist[index]);
    _playlist[index] = track;
    _currentIndex = index;
    _currentTrack = track;
    if (_isContainerItem(track)) {
      _currentContext = {
        'uri': track['uri'],
        'title': track['name'],
        'subtitle': track['artist'] ?? track['album'] ?? '',
        'type': track['item_type'] ?? 'playlist',
      };
      _contextQueue = [];
    } else if (_contextQueue.isEmpty) {
      _currentContext = null;
    }
    _position = Duration.zero;
    _duration = Duration(milliseconds: _durationFromTrack(track));
    _isLoading = true;
    _errorMessage = null;
    _dragPreviewPosition = null;
    _setPlaybackStatus(null);
    notifyListeners();

    if (preferInstantPreview && _hasPreview(track)) {
      unawaited(_warmSpotifyPlaybackForTrack(track));
      await _playPreview(track);
      return;
    }

    if (_supportsSpotifyRemotePlayback(track)) {
      await _stopPreviewPlayback();
      final appRemoteError = await _playSpotifyViaAppRemote(track);
      if (appRemoteError == null) {
        notifyListeners();
        return;
      }

      final webPlaybackError = await _playSpotifyViaWebApi(track);
      if (webPlaybackError == null) {
        unawaited(_refreshSpotifyPlaybackStateFromBackend());
        notifyListeners();
        return;
      }

      _isUsingSpotifyRemote = false;
      _isUsingSpotifyAppRemote = false;
      _isLoading = false;
      _errorMessage = appRemoteError == webPlaybackError
          ? webPlaybackError
          : '$appRemoteError\n\nFallback: $webPlaybackError';
      _setPlaybackStatus(
        _hasPreview(track) ? null : 'spotify_background_unavailable',
        _errorMessage,
      );
      if (!_hasPreview(track)) {
        notifyListeners();
        return;
      }
    }

    await _playPreview(track);
  }

  Future<void> playQueueItem(Map<String, dynamic> track, int index) async {
    if (_contextQueue.isEmpty) {
      await playTrackAtIndex(index);
      return;
    }

    final normalizedTrack = normalizeTrack(track);
    final uri = normalizedTrack['uri']?.toString() ?? '';
    if (uri.isEmpty || !_spotifyRemote.isSupportedPlatform) {
      _errorMessage =
          'This queue item is not directly playable inside the app.';
      notifyListeners();
      return;
    }

    _currentIndex = index;
    _currentTrack = {
      ...?_currentTrack,
      ...normalizedTrack,
    };
    _position = Duration.zero;
    _duration = Duration(milliseconds: _durationFromTrack(normalizedTrack));
    _isLoading = true;
    _errorMessage = null;
    _dragPreviewPosition = null;
    _setPlaybackStatus(null);
    notifyListeners();

    await _stopPreviewPlayback();
    final appRemoteError = await _playSpotifyViaAppRemote(normalizedTrack);
    if (appRemoteError == null) {
      notifyListeners();
      return;
    }

    final webPlaybackError = await _playSpotifyViaWebApi(normalizedTrack);
    if (webPlaybackError == null) {
      unawaited(_refreshSpotifyPlaybackStateFromBackend());
      notifyListeners();
      return;
    }

    _isUsingSpotifyRemote = false;
    _isUsingSpotifyAppRemote = false;
    _isLoading = false;
    _errorMessage = appRemoteError == webPlaybackError
        ? webPlaybackError
        : '$appRemoteError\n\nFallback: $webPlaybackError';
    _setPlaybackStatus('spotify_background_unavailable', _errorMessage);
    notifyListeners();
  }

  Future<void> togglePlayPause() async {
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      final wasPlaying = _isPlaying;
      _applyOptimisticRemoteTransportState(isPlaying: !wasPlaying);
      final succeeded = await _controlSpotifyPlayback(
        wasPlaying ? 'pause' : 'resume',
      );
      if (!succeeded) {
        _applyOptimisticRemoteTransportState(
          isPlaying: wasPlaying,
          clearError: false,
        );
      }
      return;
    }

    if (_supportsSpotifyRemotePlayback(_currentTrack) &&
        !_hasPreview(_currentTrack ?? const <String, dynamic>{})) {
      if (_contextQueue.isNotEmpty && _currentTrack != null) {
        await playQueueItem(_currentTrack!, _currentIndex);
      } else {
        await playTrackAtIndex(_currentIndex);
      }
      return;
    }

    if (_isPlaying) {
      await _player.pause();
    } else {
      await _player.play();
    }
  }

  Future<void> next() async {
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      _trackListened();
      if (_shouldControlRemoteRecommendationQueueLocally) {
        final nextIndex = _computeNextLocalIndex();
        if (nextIndex != null) {
          await playTrackAtIndex(nextIndex);
          return;
        }
        _onPlaylistFinished();
        return;
      }
      final snapshot = _capturePlaybackSnapshot();
      final optimisticIndex = _canOptimisticallyNavigateRemoteQueue
          ? _computeNextLocalIndex()
          : null;
      if (optimisticIndex != null) {
        _applyOptimisticQueueSelection(
          optimisticIndex,
          statusDetail: 'Skipping to the next track...',
        );
      }
      final succeeded = await _controlSpotifyPlayback('next');
      if (succeeded) {
        if (optimisticIndex == null) {
          _setPlaybackStatus(
            'spotify_queue_loading',
            'Syncing the next Spotify track in the background.',
          );
          notifyListeners();
        }
        unawaited(
          _refreshSpotifyPlaybackStateFromBackend(
            delay: const Duration(milliseconds: 150),
          ),
        );
      } else if (optimisticIndex != null) {
        _restorePlaybackSnapshot(snapshot);
      }
      return;
    }

    _trackListened();
    final nextIndex = _computeNextLocalIndex();
    if (nextIndex != null) {
      await playTrackAtIndex(nextIndex);
      return;
    }
    _onPlaylistFinished();
  }

  Future<void> previous() async {
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack) &&
        _shouldControlRemoteRecommendationQueueLocally) {
      if (_position > const Duration(seconds: 3)) {
        await playTrackAtIndex(_currentIndex);
        return;
      }

      final previousIndex = _computePreviousLocalIndex();
      if (previousIndex != null) {
        await playTrackAtIndex(previousIndex);
      }
      return;
    }

    if (_position > const Duration(seconds: 3) &&
        !(_isUsingSpotifyRemote &&
            _supportsSpotifyRemotePlayback(_currentTrack))) {
      await seekTo(Duration.zero);
      return;
    }

    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      final snapshot = _capturePlaybackSnapshot();
      final optimisticIndex = _canOptimisticallyNavigateRemoteQueue
          ? _computePreviousLocalIndex()
          : null;
      if (optimisticIndex != null) {
        _applyOptimisticQueueSelection(
          optimisticIndex,
          statusDetail: 'Going back to the previous track...',
        );
      }
      final succeeded = await _controlSpotifyPlayback('previous');
      if (succeeded) {
        if (optimisticIndex == null) {
          _setPlaybackStatus(
            'spotify_queue_loading',
            'Syncing the previous Spotify track in the background.',
          );
          notifyListeners();
        }
        unawaited(
          _refreshSpotifyPlaybackStateFromBackend(
            delay: const Duration(milliseconds: 150),
          ),
        );
      } else if (optimisticIndex != null) {
        _restorePlaybackSnapshot(snapshot);
      }
      return;
    }

    final previousIndex = _computePreviousLocalIndex();
    if (previousIndex != null) {
      await playTrackAtIndex(previousIndex);
    }
  }

  Future<void> seekTo(Duration position) async {
    final targetPosition = _clampPosition(position);
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      final previousPosition = _position;
      _position = targetPosition;
      _errorMessage = null;
      _spotifyStateTickCount = 0;
      notifyListeners();
      final succeeded = await _controlSpotifyPlayback(
        'seek',
        positionMs: targetPosition.inMilliseconds,
      );
      if (!succeeded) {
        _position = previousPosition;
        notifyListeners();
      }
      return;
    }
    _position = targetPosition;
    notifyListeners();
    await _player.seek(targetPosition);
  }

  void beginSeekPreview() {
    _dragPreviewPosition = displayPosition;
    notifyListeners();
  }

  void updateSeekPreview(Duration position) {
    _dragPreviewPosition = _clampPosition(position);
    notifyListeners();
  }

  Future<void> commitSeekPreview(Duration position) async {
    final targetPosition = _clampPosition(position);
    _dragPreviewPosition = targetPosition;
    _position = targetPosition;
    _isSeekInProgress = true;
    notifyListeners();
    try {
      await seekTo(targetPosition);
    } finally {
      _isSeekInProgress = false;
      _dragPreviewPosition = null;
      notifyListeners();
    }
  }

  void cancelSeekPreview() {
    if (_dragPreviewPosition == null) {
      return;
    }
    _dragPreviewPosition = null;
    notifyListeners();
  }

  Future<void> toggleShuffle() async {
    final nextValue = !_shuffleEnabled;
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      final previousValue = _shuffleEnabled;
      _shuffleEnabled = nextValue;
      _errorMessage = null;
      notifyListeners();
      final succeeded = await _controlSpotifyViaWebApi(
        'shuffle',
        shuffleEnabled: nextValue,
      );
      if (!succeeded) {
        _shuffleEnabled = previousValue;
        notifyListeners();
      }
      return;
    }
    _shuffleEnabled = nextValue;
    notifyListeners();
  }

  Future<void> cycleRepeatMode() async {
    final nextMode = switch (_repeatMode) {
      'off' => 'context',
      'context' => 'track',
      _ => 'off',
    };
    if (_isUsingSpotifyRemote &&
        _supportsSpotifyRemotePlayback(_currentTrack)) {
      final previousMode = _repeatMode;
      _repeatMode = nextMode;
      _errorMessage = null;
      notifyListeners();
      final succeeded = await _controlSpotifyViaWebApi(
        'repeat',
        repeatMode: nextMode,
      );
      if (!succeeded) {
        _repeatMode = previousMode;
        notifyListeners();
      }
      return;
    }
    _repeatMode = nextMode;
    notifyListeners();
  }

  Future<bool?> toggleFavoriteForCurrentTrack() async {
    final track = _currentTrack;
    final trackId = track?['id']?.toString().trim() ?? '';
    final itemType =
        track?['item_type']?.toString().trim().toLowerCase() ?? 'track';
    if (track == null || trackId.isEmpty || _favoritesBusy) {
      return null;
    }
    if (itemType != 'track') {
      _errorMessage = 'Only individual songs can be added to favorites.';
      notifyListeners();
      return null;
    }

    _favoritesBusy = true;
    final wasFavorite = isFavoriteTrack(track);
    if (wasFavorite) {
      _favoriteTrackIds.remove(trackId);
    } else {
      _favoriteTrackIds.add(trackId);
    }
    _errorMessage = null;
    notifyListeners();
    try {
      if (wasFavorite) {
        await ApiService.removeFavorite(trackId);
        _errorMessage = null;
        notifyListeners();
        return false;
      }

      await ApiService.addFavorite({
        'spotify_track_id': trackId,
        'track_name': track['name'],
        'artist_name': track['artist'],
        'album_name': track['album'] ?? '',
        'album_image': track['image'] ?? '',
        'preview_url': track['preview_url'],
        'duration_ms': track['duration_ms'] ?? 0,
      });
      _errorMessage = null;
      notifyListeners();
      return true;
    } catch (_) {
      if (wasFavorite) {
        _favoriteTrackIds.add(trackId);
      } else {
        _favoriteTrackIds.remove(trackId);
      }
      _errorMessage = 'Could not update favorites right now.';
      notifyListeners();
      return null;
    } finally {
      _favoritesBusy = false;
    }
  }

  Future<void> refreshFavorites() async {
    try {
      final favorites = await ApiService.getFavorites();
      _favoriteTrackIds
        ..clear()
        ..addAll(
          favorites
              .whereType<Map>()
              .map((favorite) =>
                  favorite['spotify_track_id']?.toString().trim() ?? '')
              .where((trackId) => trackId.isNotEmpty),
        );
      _favoritesLoaded = true;
      notifyListeners();
    } catch (_) {
      if (!_favoritesLoaded) {
        _favoriteTrackIds.clear();
      }
    }
  }

  bool isFavoriteTrack(Map<String, dynamic>? track) {
    final trackId = track?['id']?.toString().trim() ?? '';
    if (trackId.isEmpty) {
      return false;
    }
    return _favoriteTrackIds.contains(trackId);
  }

  Future<void> _playPreview(Map<String, dynamic> track) async {
    try {
      final previewUrl = track['preview_url'];
      if (previewUrl != null && previewUrl.toString().isNotEmpty) {
        unawaited(_pauseRemotePlayback());
        _isUsingSpotifyRemote = false;
        _isUsingSpotifyAppRemote = false;
        final usedPreparedSource = await _seekPreparedPreviewForCurrentTrack();
        if (!usedPreparedSource) {
          await _player.setUrl(previewUrl.toString());
        }
        await _player.play();
        _isPlaying = true;
        _setPlaybackStatus(
          'preview_local',
          'This is a local preview clip. Full playback still needs Spotify in the background.',
        );
      } else {
        _errorMessage = _isContainerItem(track)
            ? 'This Spotify playlist is still being resolved. Try again in a moment.'
            : 'This recommendation is not directly playable inside the app.';
        _setPlaybackStatus('not_directly_playable', _errorMessage);
      }
    } catch (error) {
      _errorMessage = 'Error playing track: $error';
      _setPlaybackStatus('preview_error', _errorMessage);
    }

    _isLoading = false;
    notifyListeners();
  }

  bool _supportsSpotifyRemotePlayback(Map<String, dynamic>? track) {
    if (track == null || !_spotifyRemote.isSupportedPlatform) {
      return false;
    }
    final uri = track['uri']?.toString() ?? '';
    return uri.isNotEmpty;
  }

  bool get _shouldSurfaceResolvedRemoteTrack {
    if (_currentTrack == null ||
        _contextQueue.isNotEmpty ||
        !_isUsingSpotifyRemote) {
      return false;
    }
    if (_playlist.length != 1 || !_isContainerItem(_playlist.first)) {
      return false;
    }
    return !_isContainerItem(_currentTrack!);
  }

  bool get _shouldControlRemoteRecommendationQueueLocally {
    final track = _currentTrack;
    if (!_isUsingSpotifyRemote || track == null) {
      return false;
    }
    if (_contextQueue.isNotEmpty || _isContainerItem(track)) {
      return false;
    }
    return _playlist.any((item) => !_isContainerItem(item));
  }

  bool _hasPreview(Map<String, dynamic> track) {
    final previewUrl = track['preview_url'];
    return previewUrl != null && previewUrl.toString().isNotEmpty;
  }

  int _durationFromTrack(Map<String, dynamic> track) {
    return (track['duration_ms'] as num?)?.toInt() ?? 0;
  }

  Map<String, dynamic> _capturePlaybackSnapshot() {
    return {
      'currentTrack': _currentTrack == null
          ? null
          : Map<String, dynamic>.from(_currentTrack!),
      'currentContext': _currentContext == null
          ? null
          : Map<String, dynamic>.from(_currentContext!),
      'currentIndex': _currentIndex,
      'isPlaying': _isPlaying,
      'isLoading': _isLoading,
      'position': _position,
      'duration': _duration,
      'dragPreviewPosition': _dragPreviewPosition,
      'errorMessage': _errorMessage,
      'playbackStatusCode': _playbackStatusCode,
      'playbackStatusDetail': _playbackStatusDetail,
    };
  }

  void _restorePlaybackSnapshot(Map<String, dynamic> snapshot) {
    final rawTrack = snapshot['currentTrack'];
    final rawContext = snapshot['currentContext'];
    _currentTrack = rawTrack is Map
        ? normalizeTrack(Map<String, dynamic>.from(rawTrack))
        : null;
    _currentContext =
        rawContext is Map ? Map<String, dynamic>.from(rawContext) : null;
    _currentIndex = snapshot['currentIndex'] as int? ?? _currentIndex;
    _isPlaying = snapshot['isPlaying'] as bool? ?? _isPlaying;
    _isLoading = snapshot['isLoading'] as bool? ?? _isLoading;
    _position = snapshot['position'] as Duration? ?? _position;
    _duration = snapshot['duration'] as Duration? ?? _duration;
    _dragPreviewPosition = snapshot['dragPreviewPosition'] as Duration?;
    _errorMessage = snapshot['errorMessage'] as String?;
    _playbackStatusCode = snapshot['playbackStatusCode'] as String?;
    _playbackStatusDetail = snapshot['playbackStatusDetail'] as String?;
    notifyListeners();
  }

  bool get _canOptimisticallyNavigateRemoteQueue {
    if (!_isUsingSpotifyRemote ||
        _playlist.length <= 1 ||
        _currentTrack == null) {
      return false;
    }
    if (_isContainerItem(_currentTrack!) || _contextQueue.isNotEmpty) {
      return false;
    }
    final currentIdentity = _trackIdentity(_currentTrack!);
    if (currentIdentity.isEmpty) {
      return false;
    }
    return _playlist.any((track) => _trackIdentity(track) == currentIdentity);
  }

  void _applyOptimisticRemoteTransportState({
    bool? isPlaying,
    Duration? position,
    bool clearError = true,
  }) {
    if (isPlaying != null) {
      _isPlaying = isPlaying;
    }
    if (position != null) {
      _position = _clampPosition(position);
    }
    _isLoading = false;
    _dragPreviewPosition = null;
    if (clearError) {
      _errorMessage = null;
    }
    _spotifyStateTickCount = 0;
    notifyListeners();
  }

  void _applyOptimisticQueueSelection(
    int index, {
    required String statusDetail,
  }) {
    if (index < 0 || index >= _playlist.length) {
      return;
    }
    final track = normalizeTrack(_playlist[index]);
    _playlist[index] = track;
    _currentIndex = index;
    _currentTrack = track;
    if (_contextQueue.isEmpty) {
      _currentContext = null;
    }
    _position = Duration.zero;
    _duration = Duration(milliseconds: _durationFromTrack(track));
    _dragPreviewPosition = null;
    _isPlaying = true;
    _isLoading = false;
    _errorMessage = null;
    _spotifyStateTickCount = 0;
    _setPlaybackStatus('spotify_queue_loading', statusDetail);
    notifyListeners();
  }

  Future<void> _stopPreviewPlayback() async {
    try {
      await _player.stop();
    } catch (_) {
      // Ignore preview player cleanup errors before switching sources.
    }
  }

  Future<void> _pauseRemotePlayback() async {
    if (_isUsingSpotifyRemote) {
      await _controlSpotifyPlayback('pause');
    }
  }

  void _onTrackCompleted() {
    if (_isAdvancingTrack) {
      return;
    }
    _isAdvancingTrack = true;
    unawaited(_advanceAfterTrackCompletion());
  }

  Future<void> _advanceAfterTrackCompletion() async {
    try {
      if (_repeatMode == 'track') {
        await playTrackAtIndex(_currentIndex, preferInstantPreview: true);
        return;
      }
      _trackListened();
      final nextIndex = _computeNextLocalIndex();
      if (nextIndex != null) {
        await playTrackAtIndex(nextIndex, preferInstantPreview: true);
        return;
      }
      _onPlaylistFinished();
    } finally {
      _isAdvancingTrack = false;
    }
  }

  void _trackListened() {
    final track = _currentTrack;
    if (track != null && _currentEmotion != null) {
      final itemType =
          track['item_type']?.toString().trim().toLowerCase() ?? 'track';
      final artistName = track['artist']?.toString().trim() ?? '';
      final listenSecs = _position.inSeconds;
      final durationSeconds = _duration.inSeconds > 0
          ? _duration.inSeconds
          : Duration(milliseconds: _durationFromTrack(track)).inSeconds;
      final minimumTrackedListenSeconds =
          durationSeconds > 0 && durationSeconds <= 35
              ? math.max(durationSeconds - 2, 20)
              : 30;
      _totalListenTime += listenSecs;

      if (listenSecs >= minimumTrackedListenSeconds &&
          itemType == 'track' &&
          artistName.toLowerCase() != 'open in spotify') {
        _completedTrackCount += 1;
        _updateLocalSessionPlanProgress();
        unawaited(ApiService.updateListenTime(
          track['id'] ?? '',
          _currentEmotion!,
          listenSecs,
          track['name'] ?? '',
          track['artist'] ?? '',
          itemType: itemType,
          historyId: _historyId,
          trainSession: _trainOnThisSession,
        ));
        notifyListeners();
        unawaited(_maybeTriggerFeelBetterCheckin());
      }
    }
  }

  void _onPlaylistFinished() {
    _isPlaying = false;
    _isLoading = false;
    _dragPreviewPosition = null;
    _position = _duration;
    notifyListeners();
  }

  Function(Map<String, dynamic>)? onFeelBetter;

  Future<void> _maybeTriggerFeelBetterCheckin() async {
    final historyId = _historyId;
    final nextCheckpoint = _nextFeelBetterCheckpoint;
    if (historyId == null ||
        nextCheckpoint == null ||
        _feelBetterPromptOpen ||
        _completedTrackCount < nextCheckpoint) {
      return;
    }

    try {
      final result = await ApiService.checkFeelBetter(
        historyId,
        _totalListenTime,
        _completedTrackCount,
      );
      final shouldPrompt = result['should_prompt'] == true;
      final responseHistoryId = _historyIdFromResponse(result);
      if (responseHistoryId != null) {
        _historyId = responseHistoryId;
      }
      _applyResponseSessionContext(result);
      if (shouldPrompt) {
        _feelBetterPromptOpen = true;
        onFeelBetter?.call(result);
      }
      notifyListeners();
    } catch (error) {
      debugPrint('Feel better check error: $error');
    }
  }

  Future<Map<String, dynamic>?> respondFeelBetter(bool feltBetter) async {
    final historyId = _historyId;
    if (historyId == null) {
      _feelBetterPromptOpen = false;
      return null;
    }

    try {
      final result = await ApiService.respondFeelBetter(
        historyId: historyId,
        feltBetter: feltBetter,
        duration: _totalListenTime,
        tracksPlayed: _completedTrackCount,
      );
      _feelBetterPromptOpen = false;
      _applyResponseSessionContext(result);

      final responseHistoryId = _historyIdFromResponse(result);
      if (responseHistoryId != null) {
        _historyId = responseHistoryId;
      }

      final action = result['action']?.toString().trim() ?? '';
      if (feltBetter && action == 'transition_playlist') {
        final transitionTracks = normalizeTrackList(
          List<dynamic>.from(result['tracks'] ?? const []),
        );
        if (transitionTracks.isNotEmpty) {
          final responseEmotion = result['emotion']?.toString().trim() ?? '';
          final emotion = responseEmotion.isNotEmpty
              ? responseEmotion
              : (_currentEmotion ?? 'mixed');
          loadPlaylist(
            transitionTracks,
            emotion,
            historyId: _historyId,
            autoplay: false,
            sessionPlan:
                _normalizeObjectMap(result['session_plan']) ?? _sessionPlan,
            tasteProfile:
                _normalizeObjectMap(result['taste_profile']) ?? _tasteProfile,
            outcomeMode: result['outcome_mode']?.toString() ?? _outcomeMode,
            outcomeLabel: result['outcome_label']?.toString() ?? _outcomeLabel,
            outcomeDescription: result['outcome_description']?.toString() ??
                _outcomeDescription,
            trainOnThisSession: (_normalizeObjectMap(result['taste_profile']) ??
                    _tasteProfile)['train_session'] !=
                false,
          );
          _nextFeelBetterCheckpoint = _checkpointFromResponse(result) ??
              _checkpointFromSessionPlan(_sessionPlan);
          await playTrackAtIndex(0, preferInstantPreview: true);
        }
      }
      notifyListeners();
      return result;
    } catch (error) {
      _feelBetterPromptOpen = false;
      debugPrint('Feel better response error: $error');
      return null;
    }
  }

  int? _checkpointFromResponse(Map<String, dynamic> result) {
    final checkpoint = result['next_checkpoint_tracks'];
    if (checkpoint == null) {
      return null;
    }
    if (checkpoint is int) {
      return checkpoint;
    }
    if (checkpoint is num) {
      return checkpoint.toInt();
    }
    return int.tryParse(checkpoint.toString());
  }

  int? _checkpointFromSessionPlan(Map<String, dynamic>? sessionPlan) {
    final checkpoint = sessionPlan?['next_check_in_tracks'];
    if (checkpoint == null) {
      return null;
    }
    if (checkpoint is int) {
      return checkpoint;
    }
    if (checkpoint is num) {
      return checkpoint.toInt();
    }
    return int.tryParse(checkpoint.toString());
  }

  int? _historyIdFromResponse(Map<String, dynamic> result) {
    final historyId = result['history_id'];
    if (historyId is int) {
      return historyId;
    }
    if (historyId is num) {
      return historyId.toInt();
    }
    return int.tryParse(historyId?.toString() ?? '');
  }

  String _composeSpotifyControlMessage(
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

  Future<String?> _playSpotifyViaAppRemote(Map<String, dynamic> track) async {
    final uri = track['uri']?.toString().trim() ?? '';
    if (uri.isEmpty) {
      return 'EmoTune needs a valid Spotify song before playback can start.';
    }

    try {
      await _spotifyRemote.ensureSpotifyInstalled();

      try {
        final started = await _spotifyRemote.playUri(
          uri,
          showAuthView: false,
          allowForegroundLaunch: false,
        );
        if (started) {
          _markAppRemotePlaybackStarted(track);
          return null;
        }
      } on SpotifyRemoteException catch (error) {
        if (!_shouldRetrySpotifyAppRemote(error)) {
          return error.message;
        }
      }

      final started = await _spotifyRemote.playUri(
        uri,
        showAuthView: true,
        allowForegroundLaunch: true,
      );
      if (started) {
        _markAppRemotePlaybackStarted(
          track,
          detail:
              'Spotify woke up on this phone for playback. Once it stays in the background, the jump should happen less often.',
        );
        return null;
      }

      return 'Spotify could not start playback on this phone yet.';
    } on SpotifyRemoteException catch (error) {
      return error.message;
    } on ApiException catch (error) {
      return error.message;
    } catch (_) {
      return 'Spotify playback could not be started on this phone right now.';
    }
  }

  bool _shouldRetrySpotifyAppRemote(SpotifyRemoteException error) {
    return error.requiresInteractiveAuthorization ||
        error.mayNeedSpotifyWakeUp ||
        error.authPromptWasSuppressed;
  }

  void _markAppRemotePlaybackStarted(
    Map<String, dynamic> track, {
    String? detail,
  }) {
    _isUsingSpotifyRemote = true;
    _isUsingSpotifyAppRemote = true;
    _isPlaying = true;
    _isLoading = false;
    _errorMessage = null;
    _spotifyStateTickCount = 0;
    _dragPreviewPosition = null;
    _currentTrack = normalizeTrack({
      ...?_currentTrack,
      ...track,
    });
    _duration = Duration(milliseconds: _durationFromTrack(track));

    final isContainer =
        _currentTrack != null && _isContainerItem(_currentTrack!);
    _setPlaybackStatus(
      isContainer ? 'spotify_queue_loading' : 'spotify_background',
      detail ??
          (isContainer
              ? 'Opening Spotify in the background while EmoTune waits for the queue.'
              : 'Spotify is handling full playback on this phone while EmoTune stays in front.'),
    );
    unawaited(_spotifyRemote.refreshPlayerState());
  }

  Future<String?> _playSpotifyViaWebApi(Map<String, dynamic> track) async {
    final uri = track['uri']?.toString().trim() ?? '';
    if (uri.isEmpty) {
      return 'EmoTune needs a valid Spotify song before playback can start.';
    }

    try {
      await _spotifyRemote.ensureSpotifyInstalled();
      final result = await ApiService.controlSpotifyPlayback(
        action: 'play',
        uri: uri,
      );
      debugPrint(
        '[SpotifyWebApi][play] '
        'ok=${result['ok']} '
        'blocking=${result['blocking_issue']} '
        'device=${result['selected_device_name']}',
      );
      if (result['ok'] == true) {
        _isUsingSpotifyRemote = true;
        _isUsingSpotifyAppRemote = false;
        _isPlaying = true;
        _isLoading = false;
        _errorMessage = null;
        _spotifyStateTickCount = 0;
        final selectedDeviceName =
            result['selected_device_name']?.toString().trim() ?? '';
        _setPlaybackStatus(
          'spotify_background',
          selectedDeviceName.isNotEmpty
              ? 'Spotify is playing in the background on $selectedDeviceName.'
              : 'Spotify is playing in the background while EmoTune controls it.',
        );
        return null;
      }
      return _composeSpotifyControlMessage(
        result,
        defaultMessage: 'Spotify could not start playback on this device yet.',
      );
    } on SpotifyRemoteException catch (error) {
      return error.message;
    } on ApiException catch (error) {
      return error.message;
    } catch (error) {
      return 'Spotify playback could not be started right now.';
    }
  }

  void _setPlaybackStatus(String? code, [String? detail]) {
    _playbackStatusCode = code;
    _playbackStatusDetail =
        detail?.trim().isNotEmpty == true ? detail!.trim() : null;
  }

  Future<bool> _controlSpotifyPlayback(
    String action, {
    int? positionMs,
    bool? shuffleEnabled,
    String? repeatMode,
  }) async {
    if (_isUsingSpotifyAppRemote &&
        await _controlSpotifyViaAppRemote(
          action,
          positionMs: positionMs,
        )) {
      return true;
    }

    return _controlSpotifyViaWebApi(
      action,
      positionMs: positionMs,
      shuffleEnabled: shuffleEnabled,
      repeatMode: repeatMode,
    );
  }

  Future<bool> _controlSpotifyViaAppRemote(
    String action, {
    int? positionMs,
  }) async {
    if (!_isUsingSpotifyAppRemote) {
      return false;
    }

    try {
      final succeeded = switch (action) {
        'pause' => await _spotifyRemote.pause(),
        'resume' => await _spotifyRemote.resume(),
        'next' => await _spotifyRemote.skipNext(),
        'previous' => await _spotifyRemote.skipPrevious(),
        'seek' => await _spotifyRemote.seekTo(positionMs ?? 0),
        _ => false,
      };

      if (!succeeded) {
        return false;
      }

      if (action == 'pause') {
        _isPlaying = false;
      } else if (action == 'resume') {
        _isPlaying = true;
      } else if (action == 'seek' && positionMs != null) {
        _position = _clampPosition(Duration(milliseconds: positionMs));
      }

      _errorMessage = null;
      _spotifyStateTickCount = 0;
      unawaited(_spotifyRemote.refreshPlayerState());
      notifyListeners();
      return true;
    } on SpotifyRemoteException catch (error) {
      debugPrint('[SpotifyAppRemote][$action][failed] ${error.message}');
      _isUsingSpotifyAppRemote = false;
      _errorMessage = error.message;
      return false;
    } catch (error) {
      debugPrint('[SpotifyAppRemote][$action][failed] $error');
      _isUsingSpotifyAppRemote = false;
      return false;
    }
  }

  Future<bool> _controlSpotifyViaWebApi(
    String action, {
    int? positionMs,
    bool? shuffleEnabled,
    String? repeatMode,
  }) async {
    try {
      final result = await ApiService.controlSpotifyPlayback(
        action: action,
        positionMs: positionMs,
        shuffleEnabled: shuffleEnabled,
        repeatMode: repeatMode,
      );
      debugPrint(
        '[SpotifyWebApi][$action] '
        'ok=${result['ok']} '
        'blocking=${result['blocking_issue']} '
        'device=${result['selected_device_name']}',
      );
      if (result['ok'] == true) {
        if (action == 'pause') {
          _isPlaying = false;
        } else if (action == 'resume') {
          _isPlaying = true;
        } else if (action == 'seek' && positionMs != null) {
          _position = _clampPosition(Duration(milliseconds: positionMs));
        } else if (action == 'shuffle' && shuffleEnabled != null) {
          _shuffleEnabled = shuffleEnabled;
        } else if (action == 'repeat' && repeatMode != null) {
          _repeatMode = repeatMode;
        }
        _errorMessage = null;
        if (_isUsingSpotifyRemote &&
            action != 'shuffle' &&
            action != 'repeat') {
          unawaited(
            _refreshSpotifyPlaybackStateFromBackend(
              delay: action == 'seek'
                  ? const Duration(milliseconds: 100)
                  : const Duration(milliseconds: 150),
            ),
          );
        }
        notifyListeners();
        return true;
      }
      _errorMessage = _composeSpotifyControlMessage(
        result,
        defaultMessage: 'Spotify rejected the playback command.',
      );
      notifyListeners();
      return false;
    } on ApiException catch (error) {
      _errorMessage = error.message;
      notifyListeners();
      return false;
    } catch (error) {
      _errorMessage = 'Spotify playback command failed.';
      notifyListeners();
      return false;
    }
  }

  void _handleSpotifyRemoteEvent(SpotifyRemoteEvent event) {
    switch (event.type) {
      case 'connected':
        _isUsingSpotifyRemote = true;
        _isUsingSpotifyAppRemote = true;
        _errorMessage = null;
        notifyListeners();
        return;
      case 'disconnected':
        _isUsingSpotifyAppRemote = false;
        if (_isUsingSpotifyRemote) {
          _isPlaying = false;
          _isLoading = false;
          _setPlaybackStatus(
            'spotify_background_unavailable',
            'Spotify needs to reconnect on this phone before full playback can continue.',
          );
          notifyListeners();
        }
        return;
      case 'player_state':
        _applySpotifyAppRemotePlayerState(event.data);
        return;
      case 'player_context':
        _applySpotifyAppRemoteContext(event.data);
        return;
      case 'context_queue':
        _applySpotifyAppRemoteContextQueue(event.data);
        return;
      case 'error':
        debugPrint(
          '[SpotifyAppRemote][${event.data['code'] ?? 'unknown'}] '
          '${event.data['message'] ?? 'error'}',
        );
        if (_isUsingSpotifyAppRemote) {
          _errorMessage = event.data['message']?.toString().trim();
          if (_errorMessage?.isNotEmpty ?? false) {
            _setPlaybackStatus('spotify_background_unavailable', _errorMessage);
            notifyListeners();
          }
        }
        return;
      case 'debug':
        debugPrint(
          '[SpotifyAppRemote][${event.data['step'] ?? 'debug'}] '
          '${event.data['message'] ?? ''}',
        );
        return;
      default:
        return;
    }
  }

  void _applySpotifyAppRemotePlayerState(Map<String, dynamic> event) {
    final rawTrack = event['track'];
    final track = rawTrack is Map
        ? Map<String, dynamic>.from(rawTrack)
        : <String, dynamic>{};
    final durationMs = (track['duration_ms'] as num?)?.toInt() ?? 0;

    _isUsingSpotifyRemote = true;
    _isUsingSpotifyAppRemote = true;
    _isLoading = false;
    _isPlaying = event['is_paused'] != true;
    if (durationMs > 0) {
      _duration = Duration(milliseconds: durationMs);
    }
    _position = _clampPosition(
      Duration(milliseconds: (event['position_ms'] as num?)?.toInt() ?? 0),
    );
    _dragPreviewPosition = null;
    _errorMessage = null;
    _spotifyStateTickCount = 0;

    final itemUri = track['uri']?.toString().trim() ?? '';
    if (itemUri.isNotEmpty) {
      _syncCurrentTrackFromPlaybackSnapshot({
        'item_uri': itemUri,
        'item_name': track['name'],
        'artist_name': track['artist'],
        'duration_ms': track['duration_ms'],
      });
    }

    _setPlaybackStatus(
      'spotify_background',
      'Spotify is handling full playback on this phone while EmoTune stays in front.',
    );
    notifyListeners();
  }

  void _applySpotifyAppRemoteContext(Map<String, dynamic> event) {
    final rawContext = event['context'];
    if (rawContext is! Map) {
      return;
    }

    final context = Map<String, dynamic>.from(rawContext);
    final contextUri = context['uri']?.toString().trim() ?? '';
    if (contextUri.isEmpty) {
      if (_contextQueue.isEmpty) {
        _currentContext = null;
        notifyListeners();
      }
      return;
    }

    _currentContext = {
      'uri': contextUri,
      'title': context['title'] ?? _currentContext?['title'] ?? '',
      'subtitle': context['subtitle'] ?? _currentContext?['subtitle'] ?? '',
      'type': context['type'] ?? _currentContext?['type'] ?? '',
    };
    notifyListeners();
  }

  void _applySpotifyAppRemoteContextQueue(Map<String, dynamic> event) {
    final contextUri = event['context_uri']?.toString().trim() ?? '';
    final activeContextUri = _currentContext?['uri']?.toString().trim() ?? '';
    if (contextUri.isNotEmpty &&
        activeContextUri.isNotEmpty &&
        contextUri != activeContextUri) {
      return;
    }

    final rawItems = event['items'];
    _contextQueue = rawItems is List
        ? normalizeTrackList(rawItems)
        : <Map<String, dynamic>>[];

    if (_contextQueue.isNotEmpty && _currentTrack != null) {
      final currentUri = _currentTrack!['uri']?.toString().trim() ?? '';
      final currentId = _currentTrack!['id']?.toString().trim() ?? '';
      final matchedIndex = _contextQueue.indexWhere((item) {
        final itemUri = item['uri']?.toString().trim() ?? '';
        final itemId = item['id']?.toString().trim() ?? '';
        return (currentUri.isNotEmpty && itemUri == currentUri) ||
            (currentId.isNotEmpty && itemId == currentId);
      });
      if (matchedIndex >= 0) {
        _currentIndex = matchedIndex;
      }
    }

    notifyListeners();
  }

  Duration _clampPosition(Duration position) {
    if (_duration <= Duration.zero) {
      return position < Duration.zero ? Duration.zero : position;
    }
    if (position < Duration.zero) {
      return Duration.zero;
    }
    if (position > _duration) {
      return _duration;
    }
    return position;
  }

  void _tickRemotePlaybackProgress() {
    if (_dragPreviewPosition != null) {
      return;
    }
    if (!_isUsingSpotifyRemote || !_isPlaying || _isLoading) {
      return;
    }
    if (_duration <= Duration.zero) {
      return;
    }
    final nextPosition = _position + const Duration(seconds: 1);
    if (nextPosition >= _duration) {
      _position = _duration;
      notifyListeners();
      if (_shouldControlRemoteRecommendationQueueLocally) {
        _onTrackCompleted();
      } else {
        _isPlaying = false;
        notifyListeners();
      }
      return;
    }
    _position = nextPosition;
    notifyListeners();
  }

  void _scheduleSpotifyPlaybackStateRefresh() {
    if (!_isUsingSpotifyRemote || _isLoading || _isRefreshingSpotifyState) {
      return;
    }
    _spotifyStateTickCount += 1;
    if (_spotifyStateTickCount < _spotifyStateRefreshIntervalSeconds) {
      return;
    }
    _spotifyStateTickCount = 0;
    if (_isUsingSpotifyAppRemote) {
      unawaited(_spotifyRemote.refreshPlayerState());
      return;
    }
    unawaited(_refreshSpotifyPlaybackStateFromBackend());
  }

  int? _computeNextLocalIndex() {
    if (_playlist.isEmpty) {
      return null;
    }
    if (_shuffleEnabled && _playlist.length > 1) {
      var nextIndex = _currentIndex;
      while (nextIndex == _currentIndex) {
        nextIndex = _random.nextInt(_playlist.length);
      }
      return nextIndex;
    }
    if (_currentIndex < _playlist.length - 1) {
      return _currentIndex + 1;
    }
    if (_repeatMode == 'context') {
      return 0;
    }
    return null;
  }

  int? _computePreviousLocalIndex() {
    if (_playlist.isEmpty) {
      return null;
    }
    if (_currentIndex > 0) {
      return _currentIndex - 1;
    }
    if (_repeatMode == 'context') {
      return _playlist.length - 1;
    }
    return null;
  }

  void _configurePreviewQueueForPlaylist(List<Map<String, dynamic>> playlist) {
    final previewSources = <AudioSource>[];
    final sourceIndexByPlaylistIndex = List<int?>.filled(playlist.length, null);

    for (var index = 0; index < playlist.length; index += 1) {
      final previewUrl =
          playlist[index]['preview_url']?.toString().trim() ?? '';
      if (previewUrl.isEmpty) {
        continue;
      }

      sourceIndexByPlaylistIndex[index] = previewSources.length;
      previewSources.add(
        AudioSource.uri(
          Uri.parse(previewUrl),
          tag: _trackIdentity(playlist[index]),
        ),
      );
    }

    _previewSourceIndexByPlaylistIndex = sourceIndexByPlaylistIndex;
    _previewQueueVersion += 1;
    final queueVersion = _previewQueueVersion;

    if (previewSources.isEmpty) {
      _previewQueueSource = null;
      _previewQueueReady = null;
      return;
    }

    final previewQueue = ConcatenatingAudioSource(
      useLazyPreparation: true,
      children: previewSources,
    );
    _previewQueueSource = previewQueue;
    _previewQueueReady = _preparePreviewQueue(
      previewQueue,
      queueVersion: queueVersion,
    );
    unawaited(_previewQueueReady!);
  }

  void _extendPreviewQueueForMergedPlaylist({
    required int previousPlaylistLength,
    required List<Map<String, dynamic>> mergedPlaylist,
  }) {
    if (mergedPlaylist.length <= previousPlaylistLength) {
      return;
    }

    final previewQueue = _previewQueueSource;
    if (previewQueue == null ||
        _previewSourceIndexByPlaylistIndex.length != previousPlaylistLength) {
      _configurePreviewQueueForPlaylist(mergedPlaylist);
      return;
    }

    final existingPreviewSourceCount = _previewSourceIndexByPlaylistIndex
        .where((index) => index != null)
        .length;
    final appendedSources = <AudioSource>[];
    for (var index = previousPlaylistLength;
        index < mergedPlaylist.length;
        index += 1) {
      final previewUrl =
          mergedPlaylist[index]['preview_url']?.toString().trim() ?? '';
      if (previewUrl.isEmpty) {
        _previewSourceIndexByPlaylistIndex.add(null);
        continue;
      }

      _previewSourceIndexByPlaylistIndex.add(
        existingPreviewSourceCount + appendedSources.length,
      );
      appendedSources.add(
        AudioSource.uri(
          Uri.parse(previewUrl),
          tag: _trackIdentity(mergedPlaylist[index]),
        ),
      );
    }

    if (appendedSources.isEmpty) {
      return;
    }

    final pendingPreparation = _previewQueueReady ?? Future<void>.value();
    _previewQueueReady = pendingPreparation.then((_) async {
      if (_previewQueueSource != previewQueue) {
        return;
      }
      try {
        await previewQueue.addAll(appendedSources);
      } catch (_) {
        _configurePreviewQueueForPlaylist(mergedPlaylist);
      }
    });
    unawaited(_previewQueueReady!);
  }

  Future<void> _preparePreviewQueue(
    ConcatenatingAudioSource previewQueue, {
    required int queueVersion,
  }) async {
    try {
      await _player.setAudioSource(previewQueue);
    } catch (_) {
      if (_previewQueueVersion != queueVersion ||
          _previewQueueSource != previewQueue) {
        return;
      }
      _previewQueueSource = null;
      _previewQueueReady = null;
      _previewSourceIndexByPlaylistIndex =
          List<int?>.filled(_playlist.length, null);
    }
  }

  Future<bool> _seekPreparedPreviewForCurrentTrack() async {
    final previewIndex = _previewSourceIndexForPlaylistIndex(_currentIndex);
    final previewQueue = _previewQueueSource;
    final pendingPreparation = _previewQueueReady;
    if (previewIndex == null ||
        previewQueue == null ||
        pendingPreparation == null) {
      return false;
    }

    try {
      await pendingPreparation.timeout(_preparedPreviewSeekTimeout);
      if (_previewQueueSource != previewQueue) {
        return false;
      }
      await _player.seek(Duration.zero, index: previewIndex);
      return true;
    } on TimeoutException {
      return false;
    } catch (_) {
      return false;
    }
  }

  int? _previewSourceIndexForPlaylistIndex(int playlistIndex) {
    if (playlistIndex < 0 ||
        playlistIndex >= _previewSourceIndexByPlaylistIndex.length) {
      return null;
    }
    return _previewSourceIndexByPlaylistIndex[playlistIndex];
  }

  Future<void> _warmSpotifyPlaybackForTrack(Map<String, dynamic>? track) async {
    if (_isWarmingSpotifyPlayback || !_supportsSpotifyRemotePlayback(track)) {
      return;
    }

    _isWarmingSpotifyPlayback = true;
    try {
      await _spotifyRemote.ensureSpotifyInstalled();
      try {
        await _spotifyRemote
            .connect(
              showAuthView: false,
              allowForegroundLaunch: false,
            )
            .timeout(_remoteWarmupTimeout);
      } catch (_) {
        // Best-effort warmup only.
      }

      try {
        await ApiService.prepareSpotifyPlayback().timeout(_remoteWarmupTimeout);
      } catch (_) {
        // Best-effort warmup only.
      }
    } catch (_) {
      // Ignore warmup failures; normal playback fallbacks still apply.
    } finally {
      _isWarmingSpotifyPlayback = false;
    }
  }

  Future<void> _refreshSpotifyPlaybackStateFromBackend({
    Duration delay = Duration.zero,
  }) async {
    if (!_isUsingSpotifyRemote ||
        _isUsingSpotifyAppRemote ||
        _isRefreshingSpotifyState) {
      return;
    }
    _isRefreshingSpotifyState = true;
    try {
      if (delay > Duration.zero) {
        await Future.delayed(delay);
      }
      final status = await ApiService.getSpotifyPlaybackDebugStatus();
      _applySpotifyPlaybackDebugStatus(status);
    } catch (error) {
      debugPrint('[SpotifyWebApi][state_refresh_failed] $error');
    } finally {
      _isRefreshingSpotifyState = false;
    }
  }

  void _applySpotifyPlaybackDebugStatus(Map<String, dynamic> status) {
    final rawCurrentPlayback = status['currently_playing'];
    final rawDevices = status['devices'];
    final currentlyPlaying = rawCurrentPlayback is Map
        ? Map<String, dynamic>.from(rawCurrentPlayback)
        : <String, dynamic>{};
    final devices = rawDevices is Map
        ? Map<String, dynamic>.from(rawDevices)
        : <String, dynamic>{};
    final recommendedAction =
        status['recommended_action']?.toString().trim() ?? '';

    final hasActiveDevice = devices['has_active_device'] == true;
    final playbackOk = currentlyPlaying['ok'] == true;

    if (!playbackOk && !hasActiveDevice) {
      _isPlaying = false;
      _isLoading = false;
      if (recommendedAction.isNotEmpty) {
        _errorMessage = recommendedAction;
        _setPlaybackStatus('spotify_background_unavailable', recommendedAction);
      }
      notifyListeners();
      return;
    }

    if (playbackOk) {
      _isUsingSpotifyRemote = true;
      _isUsingSpotifyAppRemote = false;
      _isLoading = false;
      _isPlaying = currentlyPlaying['is_playing'] == true;
      _position = _clampPosition(
        Duration(
          milliseconds: (currentlyPlaying['progress_ms'] as num?)?.toInt() ?? 0,
        ),
      );
      final durationMs =
          (currentlyPlaying['duration_ms'] as num?)?.toInt() ?? 0;
      if (durationMs > 0) {
        _duration = Duration(milliseconds: durationMs);
      }
      _dragPreviewPosition = null;
      _errorMessage = null;
      _syncCurrentTrackFromPlaybackSnapshot(currentlyPlaying);

      final deviceName = currentlyPlaying['device_name']?.toString().trim() ??
          devices['active_device_name']?.toString().trim() ??
          '';
      _setPlaybackStatus(
        'spotify_background',
        deviceName.isNotEmpty
            ? 'Spotify is playing in the background on $deviceName.'
            : 'Spotify is playing in the background while EmoTune controls it.',
      );
      notifyListeners();
      return;
    }

    if (hasActiveDevice) {
      _isUsingSpotifyRemote = true;
      _isUsingSpotifyAppRemote = false;
      _isLoading = false;
      _isPlaying = false;
      _dragPreviewPosition = null;
      _errorMessage = null;
      final deviceName = devices['active_device_name']?.toString().trim() ?? '';
      _setPlaybackStatus(
        'spotify_background',
        deviceName.isNotEmpty
            ? 'Spotify is ready in the background on $deviceName.'
            : 'Spotify is ready in the background while EmoTune controls it.',
      );
      notifyListeners();
    }
  }

  void _syncCurrentTrackFromPlaybackSnapshot(Map<String, dynamic> snapshot) {
    final itemUri = snapshot['item_uri']?.toString().trim() ?? '';
    final itemId = snapshot['item_id']?.toString().trim() ?? '';
    final itemType = snapshot['item_type']?.toString().trim() ?? 'track';
    if (itemUri.isEmpty && itemId.isEmpty) {
      return;
    }

    final matchedContextIndex = _contextQueue.indexWhere((track) {
      final trackUri = track['uri']?.toString().trim() ?? '';
      final trackId = track['id']?.toString().trim() ?? '';
      return (itemUri.isNotEmpty && trackUri == itemUri) ||
          (itemId.isNotEmpty && trackId == itemId);
    });
    final matchedPlaylistIndex = _playlist.indexWhere((track) {
      final trackUri = track['uri']?.toString().trim() ?? '';
      final trackId = track['id']?.toString().trim() ?? '';
      return (itemUri.isNotEmpty && trackUri == itemUri) ||
          (itemId.isNotEmpty && trackId == itemId);
    });
    final matchedTrack = matchedContextIndex >= 0
        ? _contextQueue[matchedContextIndex]
        : matchedPlaylistIndex >= 0
            ? _playlist[matchedPlaylistIndex]
            : null;

    final syncedTrack = <String, dynamic>{
      if (matchedTrack != null) ...matchedTrack,
      ...?_currentTrack,
      'id': itemId.isNotEmpty ? itemId : (_currentTrack?['id'] ?? itemUri),
      'item_type': itemType,
      'uri': itemUri.isNotEmpty ? itemUri : _currentTrack?['uri'],
      'spotify_url': itemId.isNotEmpty
          ? 'https://open.spotify.com/$itemType/$itemId'
          : (_currentTrack?['spotify_url'] ?? ''),
      'name': snapshot['item_name'] ?? _currentTrack?['name'] ?? '',
      'artist': snapshot['artist_name'] ?? _currentTrack?['artist'] ?? '',
      'album': snapshot['album_name'] ?? _currentTrack?['album'],
      'image': snapshot['image_url'] ?? _currentTrack?['image'],
      'duration_ms':
          snapshot['duration_ms'] ?? _currentTrack?['duration_ms'] ?? 0,
      'preview_url': _currentTrack?['preview_url'],
    };

    _currentTrack = normalizeTrack(syncedTrack);
    if (matchedContextIndex >= 0) {
      _currentIndex = matchedContextIndex;
    } else if (matchedPlaylistIndex >= 0) {
      _currentIndex = matchedPlaylistIndex;
    }

    final contextUri = snapshot['context_uri']?.toString().trim() ?? '';
    final contextType = snapshot['context_type']?.toString().trim() ?? '';
    if (contextUri.isNotEmpty) {
      _currentContext = {
        'uri': contextUri,
        'type': contextType,
        'title': _currentContext?['title'] ?? _currentTrack?['name'] ?? '',
        'subtitle':
            _currentContext?['subtitle'] ?? _currentTrack?['artist'] ?? '',
      };
    } else if (_contextQueue.isEmpty) {
      _currentContext = null;
    }
  }

  @override
  void dispose() {
    _spotifyRemoteEventsSubscription?.cancel();
    _remotePlaybackProgressTimer?.cancel();
    _player.dispose();
    super.dispose();
  }
}
