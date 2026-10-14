import 'package:flutter/foundation.dart';

import '../services/api_service.dart';
import '../services/spotify_remote_service.dart';

/// Tracks whether Spotify background playback is blocked for this account
/// (not approved, no Premium) and caches that check for a few minutes.
/// Pulled out of [PlayerProvider] because — unlike playback, queue
/// navigation, and Spotify remote sync, which all read and write the same
/// core playback state — this only tracks its own blocked/reason pair and
/// is read-only from the rest of the provider (aside from [markBlocked],
/// called from the App Remote / Web API failure paths), so it can be a
/// self-contained collaborator.
class SpotifyAvailabilityTracker {
  SpotifyAvailabilityTracker({
    required SpotifyRemoteService spotifyRemote,
    required this.onChanged,
  }) : _spotifyRemote = spotifyRemote;

  final SpotifyRemoteService _spotifyRemote;
  final VoidCallback onChanged;

  static const Duration _recheckInterval = Duration(minutes: 5);

  bool _isBlocked = false;
  String? _blockedReason;
  DateTime? _checkedAt;
  Future<void>? _inFlightCheck;

  bool get isBlocked => _isBlocked;
  String? get blockedReason => _blockedReason;

  /// Force a fresh availability check now, bypassing the cache interval.
  /// Call this after the user reconnects Spotify or fixes an account issue.
  /// Also clears Spotify's interactive-auth cooldown, so the Allow prompt can
  /// show again straight away.
  Future<void> retry() {
    _spotifyRemote.resetInteractiveAuthCooldown();
    return ensureChecked(force: true);
  }

  Future<void> ensureChecked({bool force = false}) async {
    if (!_spotifyRemote.isSupportedPlatform) {
      return;
    }

    final checkedAt = _checkedAt;
    if (!force &&
        checkedAt != null &&
        DateTime.now().difference(checkedAt) < _recheckInterval) {
      return;
    }

    final inFlight = _inFlightCheck;
    if (!force && inFlight != null) {
      return inFlight;
    }

    final future = _refresh();
    _inFlightCheck = future;
    try {
      await future;
    } finally {
      _inFlightCheck = null;
    }
  }

  Future<void> _refresh() async {
    try {
      final status = await ApiService.getSpotifyPlaybackDebugStatus();
      _checkedAt = DateTime.now();
      _applyStatus(status);
    } catch (error) {
      debugPrint('[SpotifyAvailability][check_failed] $error');
      // Leave any previously cached state alone; a transient failure here
      // should not permanently block background playback attempts.
    }
  }

  void _applyStatus(Map<String, dynamic> status) {
    // App Remote SDK plays through the phone's native Spotify session and
    // does not depend on EmoTune's backend OAuth link, so a missing/expired
    // backend connection is NOT treated as a playback block here — only
    // reasons that restrict the Spotify *account* itself (regardless of
    // which path is used) qualify. Backend-only problems still surface
    // through the normal Web API failure path when that fallback runs.
    final connected = status['spotify_connected'] == true;
    if (!connected) {
      _clearBlocked();
      return;
    }

    final recommendedAction =
        status['recommended_action']?.toString().trim() ?? '';
    final rawAccount = status['account'];
    final account =
        rawAccount is Map ? Map<String, dynamic>.from(rawAccount) : {};

    if (account['developer_allowlist_required'] == true) {
      markBlocked(
        recommendedAction.isNotEmpty
            ? recommendedAction
            : 'This Spotify account is not approved for EmoTune yet.',
      );
      return;
    }

    if (account['premium_status_known'] == true &&
        account['has_premium'] == false) {
      markBlocked(
        'Spotify Premium is required for full-song playback on this phone.',
      );
      return;
    }

    _clearBlocked();
  }

  void markBlocked(String reason) {
    final trimmedReason = reason.trim().isNotEmpty
        ? reason.trim()
        : 'Spotify background playback is unavailable right now.';
    final changed = !_isBlocked || _blockedReason != trimmedReason;
    _isBlocked = true;
    _blockedReason = trimmedReason;
    if (changed) {
      onChanged();
    }
  }

  void _clearBlocked() {
    if (!_isBlocked) {
      return;
    }
    _isBlocked = false;
    _blockedReason = null;
    onChanged();
  }
}
