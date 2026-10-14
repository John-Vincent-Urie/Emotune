import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_service.dart';

class AuthProvider extends ChangeNotifier {
  Map<String, dynamic>? _user;
  bool _isLoading = false;
  String? _error;

  Map<String, dynamic>? get user => _user;
  bool get isLoading => _isLoading;
  bool get isLoggedIn => _user != null;
  String? get error => _error;

  /// Drop a failed sign-in message once the user starts fixing the form, so a
  /// stale banner never sits over a field they have already corrected.
  void clearError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  Future<void>? _bootstrap;
  bool _hasSavedSession = false;

  /// True when the device still holds a session the backend has not
  /// rejected -- including when the backend could not be reached at launch,
  /// so a server that is down does not sign the user out.
  bool get hasSavedSession => _hasSavedSession;

  /// Restores the saved session once; later callers (the splash screen and
  /// main.dart both ask) share the same attempt.
  Future<void> loadUser() => _bootstrap ??= _restoreSession();

  Future<void> _restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('access_token');
    if (token == null) return;
    _hasSavedSession = true;

    _restoring = true;
    try {
      // An expired access token is renewed inside ApiService, so a 401 here
      // means the refresh token was rejected too.
      _user = await ApiService.getProfile();
      notifyListeners();
    } on ApiException catch (e) {
      // Only an auth rejection ends the session. A network error or a 5xx
      // keeps the tokens so the next launch can try again.
      if (e.statusCode == 401 || e.statusCode == 403) {
        _hasSavedSession = false;
        await logout();
      }
    } catch (_) {
      // Unexpected failure: keep the saved session rather than wipe it.
    } finally {
      _restoring = false;
    }
  }

  bool _restoring = false;

  /// ApiService could not renew the session and has already cleared the
  /// tokens. Returns whether the user was inside the app, i.e. whether the
  /// caller should send them to login; during the launch restore the splash
  /// screen does its own routing.
  bool handleSessionExpired() {
    final wasSignedIn = !_restoring && (_user != null || _hasSavedSession);
    _user = null;
    _hasSavedSession = false;
    notifyListeners();
    return wasSignedIn;
  }

  Future<bool> reloadUser() async {
    try {
      _user = await ApiService.getProfile();
      notifyListeners();
      return true;
    } catch (e) {
      return false;
    }
  }

  Future<bool> login(String email, String password) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    
    try {
      final result = await ApiService.login(email, password);
      if (result.containsKey('access')) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('access_token', result['access']);
        await prefs.setString('refresh_token', result['refresh']);
        _user = result['user'];
        _isLoading = false;
        notifyListeners();
        return true;
      } else {
        _error = result['error'] ?? 'Login failed';
        _isLoading = false;
        notifyListeners();
        return false;
      }
    } on ApiException catch (e) {
      // The server says "Invalid credentials", which reads like a system
      // fault; tell people what to check instead.
      _error = e.statusCode == 401 ? 'Wrong email or password.' : e.message;
      _isLoading = false;
      notifyListeners();
      return false;
    } catch (e) {
      _error = 'Login failed. Please try again.';
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> register(
    String displayName,
    String email,
    String password, {
    required bool acceptTerms,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    
    try {
      final result = await ApiService.register(
        displayName,
        email,
        password,
        acceptTerms: acceptTerms,
      );
      if (result.containsKey('access')) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('access_token', result['access']);
        await prefs.setString('refresh_token', result['refresh']);
        _user = result['user'];
        _isLoading = false;
        notifyListeners();
        return true;
      } else {
        _error = result.values.first.toString();
        _isLoading = false;
        notifyListeners();
        return false;
      }
    } on ApiException catch (e) {
      _error = e.message;
      _isLoading = false;
      notifyListeners();
      return false;
    } catch (e) {
      _error = 'Registration failed. Please try again.';
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    final refreshToken = prefs.getString('refresh_token');
    if (refreshToken != null && refreshToken.isNotEmpty) {
      try {
        await ApiService.logout(refreshToken);
      } catch (_) {
        // A user signing out must not be held up by a network failure. The
        // local tokens still go, and the refresh token expires on its own.
      }
    }
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
    _user = null;
    _hasSavedSession = false;
    notifyListeners();
  }

  Future<bool> updateProfile(Map<String, dynamic> data) async {
    try {
      final updated = await ApiService.updateProfile(data);
      _user = updated;
      notifyListeners();
      return true;
    } catch (e) {
      return false;
    }
  }

  void refreshUser(Map<String, dynamic> userData) {
    _user = userData;
    notifyListeners();
  }
}
