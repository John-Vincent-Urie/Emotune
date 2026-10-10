import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'support_contacts.dart';

const MethodChannel _channel = MethodChannel('emotune/dialer');

/// Opens the phone's dialer with [phone] filled in. It never places the call;
/// the user presses call themselves.
///
/// On Android this goes through MainActivity's ACTION_DIAL aimed at the
/// default dialer. A plain tel: link offered every app that registers tel:
/// (Zoom first, on QA's phone), which is the wrong moment to ask someone to
/// pick an app. Elsewhere, or if that fails, it falls back to the tel: link.
Future<bool> openDialer(String phone) async {
  final number = phone.replaceAll(RegExp(r'[^0-9+]'), '');
  if (number.isEmpty) return false;
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    try {
      final opened =
          await _channel.invokeMethod<bool>('dial', {'number': number});
      if (opened == true) return true;
    } on PlatformException {
      // Fall back to the tel: link below.
    } on MissingPluginException {
      // Fall back to the tel: link below.
    }
  }
  try {
    return await launchUrl(dialUri(number),
        mode: LaunchMode.externalApplication);
  } catch (_) {
    return false;
  }
}
