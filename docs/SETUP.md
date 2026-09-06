# Developer Setup

## 1. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Activating is a convenience, not a requirement. `backend/manage.py` and every
`ml_model/` entry point re-launch themselves under `backend/venv` when the
interpreter running them has no dependencies, so `python3 backend/manage.py
runserver` works from a plain shell, from any directory. The venv is found
relative to the script, so this holds for anyone who cloned the repo -- no
hardcoded path. Create it first: with no `backend/venv` on disk the scripts
fall through to their normal import error.

Warm the shared per-emotion candidate pools once the Spotify credentials are in
place, then keep them warm on a schedule (cron, a systemd timer, or Task
Scheduler on Windows):

```bash
python manage.py refresh_emotion_pools
```

Recommendations are served from these pools instead of waiting on a chain of
live Spotify searches. A cold pool is not fatal -- the first requests fall back
to live search and warm it themselves -- but a pool built by this command is
much deeper, so playlists keep varying between sessions. Configure it with the
`SPOTIFY_TRACK_POOL_*` variables in `.env.example`.

Backend base URL:

- local machine: `http://127.0.0.1:8000/api`
- Android emulator: `http://10.0.2.2:8000/api`

### Ranking is built in -- nothing extra to install

The music picker ranks candidates with `backend/api/picker_ranker.py`, a linear
model scored as one dot product per track. It has no native extension and no
per-request model fitting, so `pip install -r requirements.txt` is all it needs.

Its weights are data, not code. With no artifact on disk the built-in defaults
reproduce the hand-tuned blend the picker shipped with. To fit them from real
listening outcomes instead:

```bash
backend/venv/bin/python ml_model/train_picker_ranker.py
```

That writes `ml_model/artifacts/picker_weights.json`, but only if the fitted
weights beat the current defaults on held-out prompts. Point
`PICKER_RANKER_WEIGHTS_PATH` elsewhere to load a different artifact, or set
`PICKER_RANKER_ENABLED=false` to fall back to the built-in defaults.

## 2. Flutter Setup

```bash
cd flutter_app
flutter pub get
flutter run
```

Use `--dart-define=API_BASE_URL=...` when the default backend host is not correct.

Examples:

```bash
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000/api
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
flutter run --dart-define=API_BASE_URL=http://192.168.1.5:8000/api
```

For a physical Android phone connected over USB:

```bash
adb reverse tcp:8000 tcp:8000
```

## 3. Environment Variables

Copy the root `.env.example` to `.env` and fill in real values.

Required:

- `DJANGO_SECRET_KEY`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`

Recommended:

- `DJANGO_ALLOWED_HOSTS`
- `SPOTIFY_REDIRECT_URI`
- `SPOTIFY_APP_REMOTE_REDIRECT_URI`
- `EMOTION_HIGH_CONFIDENCE_THRESHOLD`
- `EMOTION_MEDIUM_CONFIDENCE_THRESHOLD`
- `EMOTION_MIN_MARGIN_THRESHOLD`

## 4. Spotify Configuration

In Spotify Developer Dashboard:

1. Open your Spotify app settings.
2. Register the redirect URI used by Django:
   `http://127.0.0.1:8000/api/spotify/callback/`
3. Register the Android App Remote redirect URI:
   `emotune://spotify-auth-callback`
4. If the app is in Development Mode, add every tester Spotify account to the dashboard allowlist.
5. Register the SHA-1 fingerprint of every signing key you build with -- see
   [Release Signing](#8-release-signing).

Notes:

- `0.0.0.0` is fine for `runserver`, but not as a Spotify redirect URI.
- The browser OAuth account, the phone Spotify app account, and the dashboard allowlisted account should all be the same account.

## 5. Emotion Model Workflow

Dataset inspection and cleaning:

```bash
cd ml_model
python inspect_dataset.py
```

Baseline model training:

```bash
cd ml_model
python train_baseline.py
```

BERT training:

```bash
cd ml_model
python train_bert.py
```

Artifacts:

- `ml_model/artifacts/data_quality_report.json`
- `ml_model/artifacts/baseline_results.json`
- `backend/ml/models/bert_emotion_model/`

## 6. Emotion Prediction Behavior

The runtime classifier now uses confidence bands:

- high confidence: trust the BERT prediction
- medium confidence: keep the BERT result but expose top emotion alternatives
- low confidence: use deterministic keyword fallback

The `/api/analyze/` response now includes:

- `top_emotions`
- `prediction_source`
- `prediction_strategy`
- `confidence_band`
- `prediction_fallback_used`
- `prediction_fallback_reason`
- `needs_review`

## 7. API Examples

### Analyze Emotion

Request:

```http
POST /api/analyze/
Content-Type: application/json
Authorization: Bearer <jwt>
```

```json
{
  "text": "I feel peaceful after a long walk."
}
```

Response:

```json
{
  "emotion": "calm",
  "confidence": 71.2,
  "top_emotions": [
    {"emotion": "calm", "confidence": 71.2},
    {"emotion": "mixed", "confidence": 14.8}
  ],
  "prediction_source": "bert",
  "prediction_strategy": "bert_high_confidence",
  "confidence_band": "high",
  "prediction_fallback_used": false,
  "needs_review": false,
  "tracks_source": "spotify",
  "tracks_fallback_used": false
}
```

### Spotify Search Failure

When Spotify blocks or rejects a request, search endpoints now return structured error details instead of an empty list.

Example:

```json
{
  "error": "Spotify track search failed.",
  "spotify": {
    "status_code": 403,
    "reason": "developer_allowlist_required",
    "message": "Check settings on https://developer.spotify.com/dashboard, the user may not be registered.",
    "recommended_action": "Spotify blocked this account because the app is still in Development Mode. Add the exact Spotify account to the Spotify Developer Dashboard user allowlist, then reconnect Spotify in EmoTune."
  }
}
```

## 8. Release Signing

Release builds are signed with a keystore that lives outside version control.
The Android SDK's debug keystore is a well-known shared key, so anything signed
with it can be impersonated by anyone; `flutter build apk --release` now refuses
to run rather than fall back to it.

`android/key.properties` and the `.jks` file it names are git-ignored. **Back
both up somewhere outside the repo.** If the keystore is lost, no future build
can update an app installed from the old one -- Android treats a differently
signed APK as a different app.

To create the keystore on a fresh machine:

```bash
cd flutter_app/android
keytool -genkeypair -v -keystore emotune-release.jks \
  -keyalg RSA -keysize 4096 -validity 10000 -alias emotune
```

Then write `flutter_app/android/key.properties`:

```properties
storePassword=<the store password you chose>
keyPassword=<the key password you chose>
keyAlias=emotune
storeFile=emotune-release.jks
```

Debug builds are unaffected and need none of this.

### Spotify and the signing fingerprint

Spotify's Android App Remote SDK authorises a client by package name **plus the
SHA-1 fingerprint of the signing key**, so a release build signed with the new
keystore is a different client to Spotify than a debug build. Register both
fingerprints in the Spotify Developer Dashboard, or App Remote will fail to
connect on release builds while working fine in debug.

Print a fingerprint with:

```bash
# release key
keytool -list -v -keystore flutter_app/android/emotune-release.jks -alias emotune
# debug key
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
```

## 9. Security Checklist

- keep `.env` local only
- rotate leaked credentials if they were ever committed
- never document real passwords in README or setup guides
- use separate Spotify apps or secrets for production if the project gets deployed
- keep the release keystore and `key.properties` out of the repo and backed up
- set `DJANGO_DEBUG=false` in any deployment; it turns on HTTPS redirects,
  HSTS, secure cookies, and closes CORS by default
- replace the placeholder `DJANGO_SECRET_KEY` before deploying

## 10. Troubleshooting

- `Cannot reach the backend`: verify Django is running on port `8000`
- `developer_allowlist_required`: add the Spotify account to the app allowlist and reconnect
- `token_invalid`: reconnect Spotify in the app
- `prediction_strategy=keyword_fallback`: the BERT model confidence was too low or the saved model was missing
