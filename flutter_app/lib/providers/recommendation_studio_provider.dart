import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RecommendationStudioProvider extends ChangeNotifier {
  static const String _sessionLengthKey = 'studio.session_length_minutes';
  static const String _familiarityKey = 'studio.familiarity';
  static const String _preferInstrumentalKey = 'studio.prefer_instrumental';
  static const String _trainOnThisSessionKey = 'studio.train_on_this_session';

  int? _sessionLengthMinutes;
  String _familiarity = 'balanced';
  bool _preferInstrumental = false;
  bool _trainOnThisSession = true;

  int? get sessionLengthMinutes => _sessionLengthMinutes;
  String get familiarity => _familiarity;
  bool get preferInstrumental => _preferInstrumental;
  bool get trainOnThisSession => _trainOnThisSession;

  Map<String, dynamic> get tasteProfile => <String, dynamic>{
        'familiarity': _familiarity,
        'prefer_instrumental': _preferInstrumental,
        'train_session': _trainOnThisSession,
      };

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _sessionLengthMinutes = prefs.getInt(_sessionLengthKey);
    _familiarity =
        prefs.getString(_familiarityKey)?.trim().isNotEmpty == true
            ? prefs.getString(_familiarityKey)!.trim()
            : 'balanced';
    _preferInstrumental = prefs.getBool(_preferInstrumentalKey) ?? false;
    _trainOnThisSession = prefs.getBool(_trainOnThisSessionKey) ?? true;
    notifyListeners();
  }

  void setSessionLengthMinutes(int? value) {
    if (_sessionLengthMinutes == value) {
      return;
    }
    _sessionLengthMinutes = value;
    notifyListeners();
    unawaited(_persist());
  }

  void setFamiliarity(String value) {
    if (_familiarity == value) {
      return;
    }
    _familiarity = value;
    notifyListeners();
    unawaited(_persist());
  }

  void setPreferInstrumental(bool value) {
    if (_preferInstrumental == value) {
      return;
    }
    _preferInstrumental = value;
    notifyListeners();
    unawaited(_persist());
  }

  void setTrainOnThisSession(bool value) {
    if (_trainOnThisSession == value) {
      return;
    }
    _trainOnThisSession = value;
    notifyListeners();
    unawaited(_persist());
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await _writeNullableInt(prefs, _sessionLengthKey, _sessionLengthMinutes);
    await prefs.setString(_familiarityKey, _familiarity);
    await prefs.setBool(_preferInstrumentalKey, _preferInstrumental);
    await prefs.setBool(_trainOnThisSessionKey, _trainOnThisSession);
  }

  Future<void> _writeNullableInt(
    SharedPreferences prefs,
    String key,
    int? value,
  ) async {
    if (value == null) {
      await prefs.remove(key);
      return;
    }
    await prefs.setInt(key, value);
  }
}
