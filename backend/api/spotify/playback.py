"""
Spotify playback control: device transfer, prepare-playback orchestration,
and executing play/pause/seek/skip/volume commands against the Web API.
"""
import logging
import time

from django.conf import settings
from django.utils import timezone

from .utils import (
    _compact_failure,
    _developer_allowlist_message,
    _has_developer_allowlist_issue,
    _normalize_scopes,
    _requested_scopes,
    _required_playback_scopes,
    _safe_int,
)

logger = logging.getLogger('api.spotify_service')


class SpotifyPlaybackClient:
    def __init__(self, service):
        self.service = service

    def _choose_transfer_device(self, devices, preferred_device_id=None):
        candidates = [
            device for device in (devices or [])
            if device.get('id') and not device.get('is_restricted')
        ]
        if not candidates:
            return None

        preferred_device_id = str(preferred_device_id or '').strip()
        if preferred_device_id:
            for device in candidates:
                if str(device.get('id')) == preferred_device_id:
                    return device

        device_priority = {
            'smartphone': 0,
            'tablet': 1,
            'computer': 2,
            'speaker': 3,
            'tv': 4,
        }
        return sorted(
            candidates,
            key=lambda device: (
                device_priority.get(str(device.get('type') or '').lower(), 99),
                str(device.get('name') or '').lower(),
            ),
        )[0]

    def get_playback_debug_status(self, user):
        """Return a structured snapshot of Spotify auth and playback readiness."""
        granted_scopes = _normalize_scopes(user.spotify_granted_scopes)
        required_scopes = _required_playback_scopes()
        diagnostics = {
            'spotify_connected': bool(user.is_spotify_connected),
            'oauth': {
                'client_id_configured': bool(self.service.client_id),
                'redirect_uri': self.service.redirect_uri,
                'app_remote_redirect_uri': getattr(
                    settings,
                    'SPOTIFY_APP_REMOTE_REDIRECT_URI',
                    '',
                ),
                'requested_scopes': _requested_scopes(),
                'granted_scopes': granted_scopes,
                'required_playback_scopes': required_scopes,
                'missing_required_scopes': [],
                'has_required_playback_scopes': False,
            },
            'token': {
                'has_access_token': bool(str(user.spotify_access_token or '').strip()),
                'has_refresh_token': bool(str(user.spotify_refresh_token or '').strip()),
                'expires_at': user.spotify_token_expires.isoformat()
                if user.spotify_token_expires
                else None,
                'is_expired': bool(
                    user.spotify_token_expires
                    and user.spotify_token_expires <= timezone.now()
                ),
                'is_valid': False,
                'refresh_attempted': False,
                'refresh_succeeded': False,
                'refresh_error': None,
                'refresh_failure': None,
            },
            'account': {
                'ok': False,
                'status_code': None,
                'stored_id': user.spotify_id,
                'product': None,
                'id': None,
                'email': None,
                'display_name': None,
                'country': None,
                'premium_required': True,
                'has_premium': None,
                'premium_status_known': False,
                'developer_allowlist_required': False,
                'account_mismatch': False,
                'error': None,
                'error_code': None,
                'error_reason': None,
                'raw_error': None,
                'response_text': None,
            },
            'devices': {
                'ok': False,
                'status_code': None,
                'device_count': 0,
                'has_active_device': False,
                'active_device_id': None,
                'active_device_name': None,
                'transfer_target_device_id': None,
                'transfer_target_device_name': None,
                'devices': [],
                'error': None,
                'error_code': None,
                'error_reason': None,
                'developer_allowlist_required': False,
                'raw_error': None,
                'response_text': None,
            },
            'currently_playing': {
                'ok': False,
                'status_code': None,
                'is_playing': False,
                'progress_ms': 0,
                'item_id': None,
                'item_name': None,
                'item_type': None,
                'artist_names': [],
                'artist_name': None,
                'album_name': None,
                'duration_ms': 0,
                'image_url': None,
                'device_id': None,
                'device_name': None,
                'context_type': None,
                'context_uri': None,
                'item_uri': None,
                'error': None,
                'error_code': None,
                'error_reason': None,
                'developer_allowlist_required': False,
                'raw_error': None,
                'response_text': None,
            },
            'recommended_action': None,
        }

        token_details = self.service.ensure_valid_token_with_details(user)
        token = token_details.get('access_token')
        diagnostics['token']['is_valid'] = bool(token)
        diagnostics['token']['is_expired'] = bool(
            user.spotify_token_expires
            and user.spotify_token_expires <= timezone.now()
        )
        diagnostics['token']['refresh_attempted'] = bool(
            token_details.get('refresh_attempted')
        )
        diagnostics['token']['refresh_succeeded'] = bool(
            token_details.get('refresh_succeeded')
        )
        diagnostics['token']['refresh_error'] = token_details.get('refresh_error')
        diagnostics['token']['refresh_failure'] = token_details.get('refresh_failure')
        diagnostics['oauth']['granted_scopes'] = _normalize_scopes(
            token_details.get('granted_scopes')
        )
        diagnostics['oauth']['missing_required_scopes'] = [
            scope for scope in required_scopes
            if scope not in diagnostics['oauth']['granted_scopes']
        ]
        diagnostics['oauth']['has_required_playback_scopes'] = not diagnostics['oauth'][
            'missing_required_scopes'
        ]

        if not user.is_spotify_connected:
            diagnostics['recommended_action'] = (
                'Connect Spotify from the EmoTune profile screen first.'
            )
            return diagnostics

        if not token:
            refresh_failure = token_details.get('refresh_failure') or {}
            diagnostics['recommended_action'] = (
                refresh_failure.get('recommended_action')
                or 'Reconnect Spotify in EmoTune because the access token is missing or refresh failed.'
            )
            return diagnostics

        profile_result = self.service.get_user_profile_result(token)
        diagnostics['account']['status_code'] = profile_result.get('status_code')
        diagnostics['account']['response_text'] = profile_result.get('response_text')
        if profile_result['ok']:
            profile = profile_result.get('data') or {}
            product = str(profile.get('product') or '').strip().lower()
            live_spotify_id = profile.get('id') or user.spotify_id
            stored_spotify_id = str(user.spotify_id or '').strip() or None
            account_mismatch = bool(
                stored_spotify_id and live_spotify_id and stored_spotify_id != live_spotify_id
            )
            if account_mismatch:
                logger.warning(
                    "Spotify account mismatch for user=%s stored_id=%s live_id=%s",
                    user.id,
                    stored_spotify_id,
                    live_spotify_id,
                )
            diagnostics['account'].update({
                'ok': True,
                'product': product or None,
                'id': live_spotify_id,
                'email': profile.get('email'),
                'display_name': profile.get('display_name'),
                'country': profile.get('country'),
                'premium_status_known': bool(product),
                'has_premium': product == 'premium',
                'account_mismatch': account_mismatch,
            })
        else:
            diagnostics['account'].update({
                'error': profile_result.get('error'),
                'error_code': profile_result.get('error_code'),
                'error_reason': profile_result.get('reason'),
                'raw_error': profile_result.get('response_json'),
                'developer_allowlist_required': (
                    profile_result.get('reason') == 'developer_allowlist_required'
                ),
            })

        current_playback_result = self.service._spotify_get(token, '/me/player/currently-playing')
        diagnostics['currently_playing']['status_code'] = current_playback_result.get(
            'status_code'
        )
        diagnostics['currently_playing']['response_text'] = current_playback_result.get(
            'response_text'
        )
        if current_playback_result['ok']:
            current_playback = current_playback_result.get('data') or {}
            device = current_playback.get('device') or {}
            item = current_playback.get('item') or {}
            context = current_playback.get('context') or {}
            album = item.get('album') or {}
            artists = item.get('artists') or []
            artist_names = [
                str(artist.get('name') or '').strip()
                for artist in artists
                if isinstance(artist, dict) and str(artist.get('name') or '').strip()
            ]
            images = album.get('images') or []
            image_url = None
            if images and isinstance(images[0], dict):
                image_url = images[0].get('url')
            diagnostics['currently_playing'].update({
                'ok': True,
                'is_playing': bool(current_playback.get('is_playing')),
                'progress_ms': _safe_int(current_playback.get('progress_ms'), 0),
                'item_id': item.get('id'),
                'item_name': item.get('name'),
                'item_type': item.get('type'),
                'artist_names': artist_names,
                'artist_name': ', '.join(artist_names) if artist_names else None,
                'album_name': album.get('name'),
                'duration_ms': _safe_int(item.get('duration_ms'), 0),
                'image_url': image_url,
                'device_id': device.get('id'),
                'device_name': device.get('name'),
                'context_type': context.get('type'),
                'context_uri': context.get('uri'),
                'item_uri': item.get('uri'),
            })
        else:
            diagnostics['currently_playing'].update({
                'error': current_playback_result.get('error'),
                'error_code': current_playback_result.get('error_code'),
                'error_reason': current_playback_result.get('reason'),
                'developer_allowlist_required': (
                    current_playback_result.get('reason') == 'developer_allowlist_required'
                ),
                'raw_error': current_playback_result.get('response_json'),
            })

        devices_result = self.service._spotify_get(token, '/me/player/devices')
        diagnostics['devices']['status_code'] = devices_result.get('status_code')
        diagnostics['devices']['response_text'] = devices_result.get('response_text')
        if devices_result['ok']:
            devices = (devices_result.get('data') or {}).get('devices', [])
            normalized_devices = [{
                'id': device.get('id'),
                'name': device.get('name'),
                'type': device.get('type'),
                'is_active': device.get('is_active', False),
                'is_restricted': device.get('is_restricted', False),
            } for device in devices]
            active_device = next(
                (device for device in normalized_devices if device.get('is_active')),
                None,
            )
            transfer_target = self.service._choose_transfer_device(normalized_devices)
            diagnostics['devices'].update({
                'ok': True,
                'device_count': len(normalized_devices),
                'has_active_device': active_device is not None,
                'active_device_id': active_device.get('id') if active_device else None,
                'active_device_name': active_device.get('name') if active_device else None,
                'transfer_target_device_id': transfer_target.get('id')
                if transfer_target
                else None,
                'transfer_target_device_name': transfer_target.get('name')
                if transfer_target
                else None,
                'devices': normalized_devices,
            })
        else:
            diagnostics['devices'].update({
                'error': devices_result.get('error'),
                'error_code': devices_result.get('error_code'),
                'error_reason': devices_result.get('reason'),
                'developer_allowlist_required': (
                    devices_result.get('reason') == 'developer_allowlist_required'
                ),
                'raw_error': devices_result.get('response_json'),
            })

        if diagnostics['oauth']['missing_required_scopes']:
            diagnostics['recommended_action'] = (
                'Spotify connected, but playback permission or active device is missing. '
                'Please reconnect EmoTune so Spotify can grant: '
                f"{', '.join(diagnostics['oauth']['missing_required_scopes'])}."
            )
        elif diagnostics['account']['account_mismatch']:
            diagnostics['recommended_action'] = (
                'Spotify connected, but the stored Spotify account does not match the live '
                'Spotify profile. Reconnect Spotify in EmoTune with the correct Spotify account.'
            )
        elif _has_developer_allowlist_issue(diagnostics):
            diagnostics['recommended_action'] = _developer_allowlist_message()
        elif diagnostics['account']['has_premium'] is False:
            diagnostics['recommended_action'] = (
                'Spotify Premium is required for in-app Spotify playback on Android. '
                'Log in to a Premium Spotify account on this phone.'
            )
        elif diagnostics['account']['error_reason'] == 'token_invalid':
            diagnostics['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the Spotify session is no longer valid.'
            )
        elif diagnostics['account']['ok'] is False and diagnostics['account']['error_reason']:
            diagnostics['recommended_action'] = (
                diagnostics['account']['error']
                or 'Spotify account verification failed. Check the connected Spotify account '
                'and the Spotify Developer Dashboard configuration.'
            )
        elif diagnostics['devices']['ok'] and not diagnostics['devices']['has_active_device']:
            if diagnostics['devices']['transfer_target_device_id']:
                diagnostics['recommended_action'] = (
                    'Spotify connected, but no active device is selected yet. '
                    'EmoTune will try to hand off playback to '
                    f"{diagnostics['devices']['transfer_target_device_name']} when you press play."
                )
            else:
                diagnostics['recommended_action'] = (
                    'Spotify connected, but Spotify has not exposed a playable device for this '
                    'phone yet. EmoTune can control Spotify in the background only after this '
                    'phone appears as an available Spotify playback device.'
                )
        elif diagnostics['devices']['status_code'] == 403:
            diagnostics['recommended_action'] = (
                'Reconnect Spotify in EmoTune because playback-state permission was rejected by Spotify.'
            )
        else:
            diagnostics['recommended_action'] = (
                'Open the Spotify app on this phone and approve EmoTune playback access when prompted. '
                'If no prompt appears, reconnect Spotify from the EmoTune profile screen and try again.'
            )

        return diagnostics

    def prepare_playback(self, user, device_id=None):
        """Prepare Spotify playback by validating scopes and activating a device if possible."""
        diagnostics = self.service.get_playback_debug_status(user)
        result = {
            'ok': False,
            'blocking_issue': None,
            'already_active': diagnostics['devices']['has_active_device'],
            'transfer_attempted': False,
            'transfer_succeeded': False,
            'device_activation_pending': False,
            'transfer_status_code': None,
            'transfer_error': None,
            'selected_device_id': None,
            'selected_device_name': None,
            'recommended_action': diagnostics['recommended_action'],
            'diagnostics': diagnostics,
        }

        if not diagnostics['spotify_connected']:
            result['blocking_issue'] = 'spotify_not_connected'
            return result

        if not diagnostics['token']['is_valid']:
            result['blocking_issue'] = 'token_invalid'
            return result

        if diagnostics['oauth']['missing_required_scopes']:
            result['blocking_issue'] = 'missing_scopes'
            return result

        if _has_developer_allowlist_issue(diagnostics):
            result['blocking_issue'] = 'developer_allowlist_required'
            result['recommended_action'] = _developer_allowlist_message()
            return result

        if diagnostics['account']['has_premium'] is False:
            result['blocking_issue'] = 'premium_required'
            return result

        if diagnostics['devices']['has_active_device']:
            result['ok'] = True
            result['recommended_action'] = 'Spotify playback device is ready.'
            return result

        target_device = self.service._choose_transfer_device(
            diagnostics['devices']['devices'],
            preferred_device_id=device_id,
        )
        if not target_device:
            result['blocking_issue'] = 'no_device'
            result['recommended_action'] = (
                'Spotify connected, but Spotify has not exposed a playable device for this '
                'phone yet. EmoTune can control Spotify in the background only after this '
                'phone appears as an available Spotify playback device.'
            )
            return result

        token = self.service.ensure_valid_token(user)
        if not token:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the access token expired before playback could start.'
            )
            return result

        result['transfer_attempted'] = True
        result['selected_device_id'] = target_device.get('id')
        result['selected_device_name'] = target_device.get('name')
        transfer_result = self.service._spotify_put(
            token,
            '/me/player',
            json_body={
                'device_ids': [target_device['id']],
                'play': True,
            },
        )
        result['transfer_status_code'] = transfer_result.get('status_code')
        if not transfer_result['ok']:
            result['transfer_error'] = transfer_result.get('error')
            result['recommended_action'] = (
                'Spotify connected, but Spotify rejected the playback handoff to this phone '
                'right now. EmoTune can control playback only after Spotify exposes this phone '
                'as an available playback device.'
            )
            return result

        time.sleep(0.9)
        updated_diagnostics = self.service.get_playback_debug_status(user)
        result['diagnostics'] = updated_diagnostics
        result['transfer_succeeded'] = updated_diagnostics['devices']['has_active_device']
        result['ok'] = updated_diagnostics['devices']['has_active_device']
        result['recommended_action'] = (
            'Spotify playback is ready on this phone.'
            if result['ok']
            else updated_diagnostics['recommended_action']
        )
        if not result['ok']:
            updated_devices = updated_diagnostics.get('devices') or {}
            updated_device_list = updated_devices.get('devices') or []
            selected_device_still_visible = any(
                str(device.get('id') or '') == str(target_device.get('id') or '')
                for device in updated_device_list
                if isinstance(device, dict)
            )
            if selected_device_still_visible:
                result['ok'] = True
                result['transfer_succeeded'] = True
                result['device_activation_pending'] = True
                result['recommended_action'] = (
                    'Spotify saw this phone and the playback handoff was requested. '
                    'EmoTune will retry playback on this device now.'
                )
            else:
                result['blocking_issue'] = 'no_device'
        return result

    def execute_playback_command(
        self,
        user,
        action,
        uri=None,
        device_id=None,
        position_ms=None,
        shuffle_enabled=None,
        repeat_mode=None,
    ):
        """Control Spotify playback through the Web API on the user's active device."""
        normalized_action = str(action or '').strip().lower()
        result = {
            'ok': False,
            'action': normalized_action,
            'blocking_issue': None,
            'selected_device_id': None,
            'selected_device_name': None,
            'recommended_action': None,
            'spotify_error': None,
            'playback': None,
            'preparation': None,
            'position_ms': None,
            'shuffle_enabled': None,
            'repeat_mode': None,
        }

        if normalized_action not in {
            'play',
            'pause',
            'resume',
            'next',
            'previous',
            'seek',
            'shuffle',
            'repeat',
        }:
            result['blocking_issue'] = 'unsupported_action'
            result['recommended_action'] = 'Unsupported Spotify playback action.'
            return result

        diagnostics = self.service.get_playback_debug_status(user)
        result['recommended_action'] = diagnostics.get('recommended_action')

        if not diagnostics['spotify_connected']:
            result['blocking_issue'] = 'spotify_not_connected'
            result['recommended_action'] = (
                'Connect Spotify from the EmoTune profile screen first.'
            )
            return result

        if not diagnostics['token']['is_valid']:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                diagnostics.get('recommended_action')
                or 'Reconnect Spotify in EmoTune because the Spotify access token is not valid.'
            )
            return result

        if diagnostics['oauth']['missing_required_scopes']:
            result['blocking_issue'] = 'missing_scopes'
            result['recommended_action'] = (
                diagnostics.get('recommended_action')
                or 'Reconnect Spotify in EmoTune so Spotify can grant the required playback scopes.'
            )
            return result

        if _has_developer_allowlist_issue(diagnostics):
            result['blocking_issue'] = 'developer_allowlist_required'
            result['recommended_action'] = _developer_allowlist_message()
            return result

        if diagnostics['account']['has_premium'] is False:
            result['blocking_issue'] = 'premium_required'
            result['recommended_action'] = (
                'Spotify Premium is required for remote playback control on Android.'
            )
            return result

        token = self.service.ensure_valid_token(user)
        if not token:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the Spotify session could not be refreshed.'
            )
            return result

        preparation = None
        target_device_id = None
        target_device_name = None
        request_params = None

        if normalized_action in {
            'play',
            'resume',
            'next',
            'previous',
            'seek',
            'shuffle',
            'repeat',
        }:
            preparation = self.service.prepare_playback(user, device_id=device_id)
            result['preparation'] = preparation
            if not preparation.get('ok'):
                result['blocking_issue'] = preparation.get('blocking_issue') or 'no_device'
                result['recommended_action'] = (
                    preparation.get('recommended_action')
                    or diagnostics.get('recommended_action')
                )
                return result

            target_device_id = (
                str(preparation.get('selected_device_id') or '').strip()
                or str(
                    (
                        preparation.get('diagnostics') or {}
                    ).get('devices', {}).get('active_device_id') or ''
                ).strip()
            )
            target_device_name = (
                str(preparation.get('selected_device_name') or '').strip()
                or str(
                    (
                        preparation.get('diagnostics') or {}
                    ).get('devices', {}).get('active_device_name') or ''
                ).strip()
            )
            if target_device_id:
                request_params = {'device_id': target_device_id}

        result['selected_device_id'] = target_device_id or None
        result['selected_device_name'] = target_device_name or None

        command_result = None
        if normalized_action == 'play':
            normalized_uri = str(uri or '').strip()
            if not normalized_uri.startswith('spotify:'):
                result['blocking_issue'] = 'invalid_uri'
                result['recommended_action'] = (
                    'EmoTune needs a valid Spotify URI before it can start playback.'
                )
                return result

            item_parts = normalized_uri.split(':', 2)
            item_type = item_parts[1] if len(item_parts) >= 2 else 'track'
            play_body = (
                {'uris': [normalized_uri]}
                if item_type in {'track', 'episode'}
                else {'context_uri': normalized_uri}
            )
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/play',
                params=request_params,
                json_body=play_body,
            )
        elif normalized_action == 'resume':
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/play',
                params=request_params,
            )
        elif normalized_action == 'pause':
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/pause',
            )
        elif normalized_action == 'next':
            command_result = self.service._spotify_post(
                token,
                '/me/player/next',
                params=request_params,
            )
        elif normalized_action == 'previous':
            command_result = self.service._spotify_post(
                token,
                '/me/player/previous',
                params=request_params,
            )
        elif normalized_action == 'seek':
            safe_position_ms = max(_safe_int(position_ms, 0), 0)
            result['position_ms'] = safe_position_ms
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/seek',
                params={
                    **(request_params or {}),
                    'position_ms': safe_position_ms,
                },
            )
        elif normalized_action == 'shuffle':
            normalized_shuffle = bool(shuffle_enabled)
            result['shuffle_enabled'] = normalized_shuffle
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/shuffle',
                params={
                    **(request_params or {}),
                    'state': str(normalized_shuffle).lower(),
                },
            )
        elif normalized_action == 'repeat':
            normalized_repeat_mode = str(repeat_mode or '').strip().lower()
            if normalized_repeat_mode not in {'off', 'track', 'context'}:
                result['blocking_issue'] = 'invalid_repeat_mode'
                result['recommended_action'] = (
                    'Repeat mode must be one of: off, track, context.'
                )
                return result
            result['repeat_mode'] = normalized_repeat_mode
            command_result = self.service._spotify_request(
                'PUT',
                token,
                '/me/player/repeat',
                params={
                    **(request_params or {}),
                    'state': normalized_repeat_mode,
                },
            )

        if (
            command_result
            and not command_result.get('ok')
            and preparation
            and preparation.get('device_activation_pending')
            and normalized_action in {'play', 'resume', 'seek', 'shuffle', 'repeat'}
        ):
            time.sleep(1.1)
            if normalized_action == 'play':
                normalized_uri = str(uri or '').strip()
                item_parts = normalized_uri.split(':', 2)
                item_type = item_parts[1] if len(item_parts) >= 2 else 'track'
                play_body = (
                    {'uris': [normalized_uri]}
                    if item_type in {'track', 'episode'}
                    else {'context_uri': normalized_uri}
                )
                command_result = self.service._spotify_request(
                    'PUT',
                    token,
                    '/me/player/play',
                    params=request_params,
                    json_body=play_body,
                )
            elif normalized_action == 'resume':
                command_result = self.service._spotify_request(
                    'PUT',
                    token,
                    '/me/player/play',
                    params=request_params,
                )
            elif normalized_action == 'seek':
                command_result = self.service._spotify_request(
                    'PUT',
                    token,
                    '/me/player/seek',
                    params={
                        **(request_params or {}),
                        'position_ms': result['position_ms'] or 0,
                    },
                )
            elif normalized_action == 'shuffle':
                command_result = self.service._spotify_request(
                    'PUT',
                    token,
                    '/me/player/shuffle',
                    params={
                        **(request_params or {}),
                        'state': str(bool(result['shuffle_enabled'])).lower(),
                    },
                )
            elif normalized_action == 'repeat':
                command_result = self.service._spotify_request(
                    'PUT',
                    token,
                    '/me/player/repeat',
                    params={
                        **(request_params or {}),
                        'state': result['repeat_mode'] or 'off',
                    },
                )

        if not command_result or not command_result.get('ok'):
            result['blocking_issue'] = (
                command_result.get('reason')
                if isinstance(command_result, dict)
                else 'spotify_request_failed'
            )
            result['recommended_action'] = (
                (command_result or {}).get('recommended_action')
                or diagnostics.get('recommended_action')
                or 'Spotify rejected the playback command.'
            )
            result['spotify_error'] = _compact_failure(
                command_result or {},
                source='spotify_player',
            )
            return result

        playback_result = self.service._spotify_get(token, '/me/player/currently-playing')
        if playback_result.get('ok'):
            result['playback'] = playback_result.get('data')

        result['ok'] = True
        result['recommended_action'] = {
            'play': 'Spotify is playing the selected song on this device.',
            'resume': 'Spotify playback resumed on this device.',
            'pause': 'Spotify playback paused.',
            'next': 'Spotify skipped to the next track.',
            'previous': 'Spotify went back to the previous track.',
            'seek': 'Spotify playback jumped to the requested position.',
            'shuffle': 'Spotify shuffle mode updated.',
            'repeat': 'Spotify repeat mode updated.',
        }.get(normalized_action, 'Spotify playback command sent.')
        return result
