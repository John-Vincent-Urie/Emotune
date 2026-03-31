import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RecommendationStudioProvider extends ChangeNotifier {
  static const String _outcomeModeKey = 'studio.outcome_mode';
  static const String _sessionLengthKey = 'studio.session_length_minutes';
  static const String _checkInFrequencyKey = 'studio.check_in_frequency_tracks';
  static const String _familiarityKey = 'studio.familiarity';
  static const String _preferInstrumentalKey = 'studio.prefer_instrumental';
  static const String _trainOnThisSessionKey = 'studio.train_on_this_session';

  String _selectedOutcomeMode = 'match_mood';
  int? _sessionLengthMinutes;
  int? _checkInFrequencyTracks;
  String _familiarity = 'balanced';
  bool _preferInstrumental = false;
  bool _trainOnThisSession = true;

  String get selectedOutcomeMode => _selectedOutcomeMode;
  int? get sessionLengthMinutes => _sessionLengthMinutes;
  int? get checkInFrequencyTracks => _checkInFrequencyTracks;
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
    _selectedOutcomeMode =
        prefs.getString(_outcomeModeKey)?.trim().isNotEmpty == true
            ? prefs.getString(_outcomeModeKey)!.trim()
            : 'match_mood';
    _sessionLengthMinutes = prefs.getInt(_sessionLengthKey);
    _checkInFrequencyTracks = prefs.getInt(_checkInFrequencyKey);
    _familiarity =
        prefs.getString(_familiarityKey)?.trim().isNotEmpty == true
            ? prefs.getString(_familiarityKey)!.trim()
            : 'balanced';
    _preferInstrumental = prefs.getBool(_preferInstrumentalKey) ?? false;
    _trainOnThisSession = prefs.getBool(_trainOnThisSessionKey) ?? true;
    notifyListeners();
  }

  void setOutcomeMode(String value) {
    if (_selectedOutcomeMode == value) {
      return;
    }
    _selectedOutcomeMode = value;
    notifyListeners();
    unawaited(_persist());
  }

  void setSessionLengthMinutes(int? value) {
    if (_sessionLengthMinutes == value) {
      return;
    }
    _sessionLengthMinutes = value;
    notifyListeners();
    unawaited(_persist());
  }

  void setCheckInFrequencyTracks(int? value) {
    if (_checkInFrequencyTracks == value) {
      return;
    }
    _checkInFrequencyTracks = value;
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
    await prefs.setString(_outcomeModeKey, _selectedOutcomeMode);
    await _writeNullableInt(prefs, _sessionLengthKey, _sessionLengthMinutes);
    await _writeNullableInt(
      prefs,
      _checkInFrequencyKey,
      _checkInFrequencyTracks,
    );
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
