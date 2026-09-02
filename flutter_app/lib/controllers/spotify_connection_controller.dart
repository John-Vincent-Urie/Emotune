import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';

/// Handles connecting/disconnecting the user's Spotify account from the
/// profile screen, including the OAuth-in-browser polling wait. A
/// [ChangeNotifier] so [ProfileScreen] can rebuild its "Connect/Disconnect
/// Spotify" tiles while a request is in flight, without owning the request
/// logic itself.
class SpotifyConnectionController extends ChangeNotifier {
  bool _isConnecting = false;
  bool _isDisconnecting = false;

  bool get isConnecting => _isConnecting;
  bool get isDisconnecting => _isDisconnecting;

  Future<void> connect(BuildContext context, String userId) async {
    if (_isConnecting) {
      return;
    }

    _isConnecting = true;
    notifyListeners();

    try {
      final url = await ApiService.getSpotifyAuthUrl(userId);
      final uri = Uri.parse(url);
      final launched = await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );

      if (!context.mounted) {
        return;
      }

      if (!launched) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open Spotify login')),
        );
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Finish Spotify login in your browser, then return to the app.',
          ),
        ),
      );

      final connected = await _waitForSpotifyConnection(context);

      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            connected
                ? 'Spotify connected successfully.'
                : 'Spotify login is still pending. Return here after finishing in the browser.',
          ),
        ),
      );
    } catch (e) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Spotify connection failed')),
      );
    } finally {
      _isConnecting = false;
      notifyListeners();
    }
  }

  Future<bool> _waitForSpotifyConnection(BuildContext context) async {
    final auth = context.read<AuthProvider>();
    final deadline = DateTime.now().add(const Duration(minutes: 2));

    while (DateTime.now().isBefore(deadline)) {
      await Future.delayed(const Duration(seconds: 2));

      if (!context.mounted) {
        return false;
      }

      final reloaded = await auth.reloadUser();
      final user = auth.user;

      if (reloaded && user?['is_spotify_connected'] == true) {
        return true;
      }
    }

    return false;
  }

  Future<void> disconnect(BuildContext context) async {
    if (_isDisconnecting) {
      return;
    }

    final shouldDisconnect = await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Disconnect Spotify?'),
            content: const Text(
              'This removes the linked Spotify account from EmoTune so you can reconnect with a different account.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: const Text('Disconnect'),
              ),
            ],
          ),
        ) ??
        false;

    if (!shouldDisconnect || !context.mounted) {
      return;
    }

    _isDisconnecting = true;
    notifyListeners();

    try {
      await ApiService.disconnectSpotify();

      if (!context.mounted) {
        return;
      }

      final reloaded = await context.read<AuthProvider>().reloadUser();

      if (!context.mounted) {
        return;
      }

      if (reloaded) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Spotify disconnected from EmoTune. You can now connect a different Spotify account.',
            ),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Spotify was disconnected, but the profile did not refresh yet. Reopen the screen if needed.',
            ),
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Spotify disconnect failed: $e'),
        ),
      );
    } finally {
      _isDisconnecting = false;
      notifyListeners();
    }
  }
}
