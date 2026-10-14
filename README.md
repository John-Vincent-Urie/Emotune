# EmoTune

EmoTune is an emotion-aware music recommendation system built with Flutter and Django. It helps users describe how they feel, analyzes that emotional signal, and returns Spotify-ready music recommendations that try to match, support, or gently guide the mood.

## System Summary

EmoTune combines four main parts into one flow:

- emotion analysis from user text or an explicitly selected mood
- a BERT-first classifier with keyword fallback when the model is unavailable or uncertain
- Spotify recommendation search, ranking, and fallback handling
- a local linear ranker that orders candidates by emotion fit, personalization, and availability

In practice, the system works like this:

1. The user types a feeling or taps an emotion tab in the Flutter app.
2. The Django backend predicts the main emotion and confidence breakdown.
3. The backend generates a short supportive response for that mood.
4. Spotify candidates are fetched from personalization signals, catalog search, or curated fallbacks.
5. The recommendation engine scores tracks by emotional fit, personalization, and availability.
6. The linear picker scores every candidate and orders the playlist.
7. The app returns playable tracks, stores prompt history, and learns from favorites and listening behavior.

## Features

- 13-label emotion detection with confidence scores and top-emotion breakdowns
- hybrid Plutchik-ready emotion profile derived from the 13-label classifier for visualization and explainability
- explicit emotion-tab recommendations for users who already know the mood they want
- Spotify search, playback preparation, saved-track/top-track personalization, and curated fallbacks
- a local linear ranker with weights fitted offline from real listening outcomes
- hybrid scoring that combines emotion alignment, interaction history, and track metadata
- recommendation history, favorites, listening sessions, and preference learning
- dataset inspection, baseline experiments, and staged BERT fine-tuning scripts for the ML workflow

## Tech Stack

- Flutter
- Django REST Framework
- Simple JWT
- Spotify Web API and Spotify App Remote
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

1. Create a local env file from [.env.example](.env.example).
2. Install backend dependencies:

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

Use [.env.example](.env.example) as the template.

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
- `PICKER_RANKER_ENABLED`
- `PICKER_RANKER_WEIGHTS_PATH`
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

## Ranking

After Spotify candidate retrieval, `backend/api/picker_ranker.py` decides the
order. It scores each candidate as a weighted sum of signals the recommendation
engine already computed, so ranking a whole candidate set costs one dot product
per track -- no native extension, no per-request model fitting.

Features:

```
emotion_alignment, personalization, popularity, availability,
is_preferred, familiar_source, discovery_fit, instrumental_fit
```

The weights are data, not code. With no artifact on disk the built-in defaults
reproduce the hand-tuned blend the picker shipped with. Fit them from real
listening outcomes:

```bash
backend/venv/bin/python ml_model/train_picker_ranker.py
```

The artifact is written to `ml_model/artifacts/picker_weights.json` only if the
fitted weights beat the current defaults on held-out prompts, and splitting is
by prompt so candidates from one prompt never land on both sides.

Controlled by `PICKER_RANKER_ENABLED` and `PICKER_RANKER_WEIGHTS_PATH`.

To export raw training examples from real usage:

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
- If the Android app cannot reach Django, make sure port `8000` is reachable from the device.

See [SETUP.md](docs/SETUP.md) for the full developer guide.
