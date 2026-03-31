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

  Future<void> loadUser() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('access_token');
    if (token == null) return;
    
    try {
      _user = await ApiService.getProfile();
      notifyListeners();
    } catch (e) {
      await logout();
    }
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
      _error = e.message;
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
    bool personalizationOptIn = true,
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
        personalizationOptIn: personalizationOptIn,
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
    await prefs.remove('access_token');
    await prefs.remove('refresh_token');
    _user = null;
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
