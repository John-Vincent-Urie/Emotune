# Developer Setup

## 1. Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Backend base URL:

- local machine: `http://127.0.0.1:8000/api`
- Android emulator: `http://10.0.2.2:8000/api`

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

## 8. Security Checklist

- keep `.env` local only
- rotate leaked credentials if they were ever committed
- never document real passwords in README or setup guides
- use separate Spotify apps or secrets for production if the project gets deployed

## 9. Troubleshooting

- `Cannot reach the backend`: verify Django is running on port `8000`
- `developer_allowlist_required`: add the Spotify account to the app allowlist and reconnect
- `token_invalid`: reconnect Spotify in the app
- `prediction_strategy=keyword_fallback`: the BERT model confidence was too low or the saved model was missing
