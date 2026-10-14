import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RecommendationStudioProvider extends ChangeNotifier {
  static const String _sessionLengthKey = 'studio.session_length_minutes';
  // Familiar/Discovery, Prefer instrumental and Train on this session were
  // removed (owner decisions, 2026-10-10: the songs are the therapist's static
  // list, so there is no taste to steer and no model to train). Their old keys
  // are cleared on load so nothing stale lingers in preferences.
  static const List<String> _retiredKeys = [
    'studio.familiarity',
    'studio.prefer_instrumental',
    'studio.train_on_this_session',
  ];

  int? _sessionLengthMinutes;

  int? get sessionLengthMinutes => _sessionLengthMinutes;


  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _sessionLengthMinutes = prefs.getInt(_sessionLengthKey);
    for (final key in _retiredKeys) {
      await prefs.remove(key);
    }
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

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await _writeNullableInt(prefs, _sessionLengthKey, _sessionLengthMinutes);
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
