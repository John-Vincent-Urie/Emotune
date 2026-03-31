<<<<<<< HEAD
# EmoTune

EmoTune is an emotion-aware music recommendation system built with Flutter and Django. It helps users describe how they feel, analyzes that emotional signal, and returns Spotify-ready music recommendations that try to match, support, or gently guide the mood.

## System Summary

EmoTune combines four main parts into one flow:

- emotion analysis from user text or an explicitly selected mood
- a BERT-first classifier with keyword fallback when the model is unavailable or uncertain
- Spotify recommendation search, ranking, and fallback handling
- a local LightFM personalization layer that re-ranks candidates using user behavior and mood context

In practice, the system works like this:

1. The user types a feeling or taps an emotion tab in the Flutter app.
2. The Django backend predicts the main emotion and confidence breakdown.
3. The backend generates a short supportive response for that mood.
4. Spotify candidates are fetched from personalization signals, catalog search, or curated fallbacks.
5. The recommendation engine scores tracks by emotional fit, personalization, and availability.
6. LightFM re-ranks the candidate pool using favorites, listening history, prompt history, and the current emotion context.
7. The app returns playable tracks, stores prompt history, and learns from favorites and listening behavior.

## Features

- 13-label emotion detection with confidence scores and top-emotion breakdowns
- hybrid Plutchik-ready emotion profile derived from the 13-label classifier for visualization and explainability
- explicit emotion-tab recommendations for users who already know the mood they want
- Spotify search, playback preparation, saved-track/top-track personalization, and curated fallbacks
- local LightFM ranking for personalized playlist ordering
- hybrid scoring that combines emotion alignment, interaction history, and track metadata
- recommendation history, favorites, listening sessions, and preference learning
- dataset inspection, baseline experiments, and staged BERT fine-tuning scripts for the ML workflow

## Tech Stack

- Flutter
- Django REST Framework
- Simple JWT
- Spotify Web API and Spotify App Remote
- LightFM
- PyTorch + Transformers
- scikit-learn for baseline experiments

## Project Structure

```text
backend/
  api/                  Django API views and Spotify integration
  emotune_project/      Django settings
  ml/                   Runtime emotion classifier
  users/                Auth, profile, history, favorites
dataset/
  emotune_custom_dataset.csv
docs/
  EMOTION_LABELS.md
  SETUP.md
flutter_app/
  lib/
ml_model/
  data_pipeline.py
  inspect_dataset.py
  train_baseline.py
  train_bert.py
```

## Quick Start

1. Create a local env file from [.env.example](/c:/Users/Urie/Documents/CApstone!/EmoTune-Capstone_project/.env.example).
2. Install backend dependencies:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

3. Install Flutter dependencies and run the app:

```bash
cd flutter_app
flutter pub get
flutter run
```

For Android:

- emulator: `http://10.0.2.2:8000/api`
- physical device: use `adb reverse tcp:8000 tcp:8000` or `--dart-define=API_BASE_URL=http://YOUR_IP:8000/api`

## Environment Variables

Use [.env.example](/c:/Users/Urie/Documents/CApstone!/EmoTune-Capstone_project/.env.example) as the template.

Important variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI`
- `SPOTIFY_APP_REMOTE_REDIRECT_URI`
- `SPOTIFY_HTTP_TIMEOUT_SECONDS`
- `SPOTIFY_RECOMMENDATION_BUDGET_SECONDS`
- `LIGHTFM_RECOMMENDER_ENABLED`
- `LIGHTFM_RECOMMENDER_ALLOW_WINDOWS`
- `LIGHTFM_RECOMMENDER_LOSS`
- `LIGHTFM_RECOMMENDER_COMPONENTS`
- `LIGHTFM_RECOMMENDER_EPOCHS`
- `LIGHTFM_RECOMMENDER_MIN_INTERACTIONS`
- `EMOTION_HIGH_CONFIDENCE_THRESHOLD`
- `EMOTION_MEDIUM_CONFIDENCE_THRESHOLD`
- `EMOTION_MIN_MARGIN_THRESHOLD`
- `EMOTION_TOP_EMOTIONS_COUNT`
- `ML_MODEL_PATH`

## ML Workflow

Inspect and clean the custom dataset:

```bash
cd ml_model
python inspect_dataset.py
```

Train baseline models:

```bash
cd ml_model
python train_baseline.py
```

Train the BERT model:

```bash
cd ml_model
python train_bert.py
```

Default fine-tuning order:

1. GoEmotions base fine-tune
2. optional `dair-ai/emotion` adaptation
3. EmoTune final fine-tune on your custom dataset

Useful training toggles:

- `EMOTUNE_ENABLE_GOEMOTIONS=true`
- `EMOTUNE_ENABLE_DAIR_EMOTION=false`
- `EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE=true`
- `EMOTUNE_GOEMOTIONS_EPOCHS=1`
- `EMOTUNE_DAIR_EMOTION_EPOCHS=1`
- `EMOTUNE_FINAL_FINETUNE_EPOCHS=5`
- `EMOTUNE_CUSTOM_REPEAT_FACTOR=10`

Example with the optional middle stage enabled:

```bash
$env:EMOTUNE_ENABLE_DAIR_EMOTION='true'
python train_bert.py
```

Outputs:

- data quality report: `ml_model/artifacts/data_quality_report.json`
- baseline metrics: `ml_model/artifacts/baseline_results.json`
- BERT model: `backend/ml/models/bert_emotion_model/`
- staged training summary: `backend/ml/models/bert_emotion_model/training_results.json`

## LightFM Ranking

EmoTune now uses LightFM as the personalization and ranking layer after Spotify candidate retrieval.

Recommended production pattern:

1. Use BERT to detect the current emotion.
2. Retrieve candidate tracks from Spotify, user history, and curated fallbacks.
3. Feed the candidate set and stored user interactions into LightFM.
4. Blend LightFM scores with emotion alignment and availability signals.
5. Fall back to the heuristic ranking path if LightFM is unavailable or there is not enough interaction data yet.

This is controlled by:

- `LIGHTFM_RECOMMENDER_ENABLED`
- `LIGHTFM_RECOMMENDER_ALLOW_WINDOWS`
- `LIGHTFM_RECOMMENDER_LOSS`
- `LIGHTFM_RECOMMENDER_COMPONENTS`
- `LIGHTFM_RECOMMENDER_EPOCHS`
- `LIGHTFM_RECOMMENDER_MIN_INTERACTIONS`

To export training examples from real EmoTune usage:

```bash
cd ml_model
python export_music_picker_dataset.py
```

## API Example

`POST /api/analyze/`

Request:

```json
{
  "text": "I feel overwhelmed with everything I need to finish."
}
```

Response:

```json
{
  "emotion": "stressed",
  "confidence": 78.4,
  "plutchik_scores": {
    "fear": 61.2,
    "anticipation": 44.8,
    "anger": 12.1
  },
  "plutchik_dominant_emotion": "fear",
  "top_emotions": [
    {"emotion": "stressed", "confidence": 78.4},
    {"emotion": "fear", "confidence": 12.7}
  ],
  "prediction_source": "bert",
  "prediction_strategy": "bert_high_confidence",
  "confidence_band": "high",
  "prediction_fallback_used": false,
  "needs_review": false,
  "tracks_source": "spotify",
  "tracks_fallback_used": false,
  "tracks": []
}
```

## Security Notes

- Do not commit `.env`.
- Do not hardcode Spotify credentials or Django secret keys in source files.
- Treat `.env.example` as placeholders only.
- If the app is still in Spotify Development Mode, add the real Spotify account to the dashboard allowlist.

## Troubleshooting

- If Spotify search returns a structured `developer_allowlist_required` error, reconnect with an allowlisted Spotify account.
- If `prediction_strategy` becomes `keyword_fallback`, the model confidence was too low or the BERT model was unavailable.
- If `lightfm` fails to install on Windows, install Microsoft C++ Build Tools first because LightFM builds a native extension.
- EmoTune now disables live LightFM ranking on Windows by default because the native runtime can crash the Django process on some setups. Set `LIGHTFM_RECOMMENDER_ALLOW_WINDOWS=true` only if you have verified the local LightFM build is stable.
- If the Android app cannot reach Django, make sure port `8000` is reachable from the device.

See [SETUP.md](/c:/Users/Urie/Documents/CApstone!/EmoTune-Capstone_project/docs/SETUP.md) for the full developer guide.
=======
# Emotune
EmoTune is an emotion-aware music recommendation application built with Flutter on the client side and Django on the backend.
>>>>>>> fd365ba4ddae5ddfd1d045040b028aabc58e53a4
