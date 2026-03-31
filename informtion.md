# EmoTune Information

## 1. Project Overview

EmoTune is an emotion-aware music recommendation application built with Flutter on the client side and Django on the backend.

Its main goal is to:

- understand how the user feels from text input or an explicitly selected mood
- recommend Spotify-ready music that matches, supports, or gently shifts that mood
- learn from favorites, listening history, prompt history, and session behavior
- provide explainable emotion output through both the EmoTune label set and a Plutchik-compatible profile

EmoTune is not just a basic playlist app. It combines:

- emotion classification
- Spotify search and playback support
- personalization and re-ranking
- session-based recommendation control
- mood-aware check-ins and recovery support

## 2. Core Product Flow

The usual user flow is:

1. The user enters a prompt like "I feel overwhelmed" or taps an emotion tab.
2. EmoTune predicts the emotion and confidence distribution.
3. The backend generates a short supportive message.
4. Spotify candidates are retrieved from user music, catalog search, and fallback logic.
5. LightFM and heuristic ranking reorder the candidates.
6. The app returns playable tracks, playlist metadata, session metadata, and explainability fields.
7. Listening activity, favorites, and prompt history can be used to improve future recommendations.

## 3. User-Facing Features

Current user-facing capabilities in the project include:

- text-based emotion analysis
- explicit emotion-tab recommendations
- Spotify playback preparation and playback control
- favorites management
- listening history and emotion history
- adaptive playlist continuation
- "feel better?" recovery prompts for intense emotional states
- outcome-based recommendation modes
- session engine with timers and check-ins
- taste controls such as familiarity, instrumental preference, and training opt-out
- hybrid Plutchik-style emotion profile for explainability
- profile management, Spotify connection, and preferred artists
- dark/light theme toggle

## 4. Emotion Label Schema

EmoTune uses a custom 13-label emotion schema:

- happy
- sad
- angry
- motivational
- fear
- depressing
- surprising
- stressed
- calm
- lonely
- romantic
- nostalgic
- mixed

These labels are the app's main emotion language across:

- runtime classification
- response generation
- recommendation targeting
- training data preparation
- history and personalization

## 5. Explainability Layer

In addition to the 13 EmoTune labels, the app derives a secondary Plutchik-compatible emotion profile.

This means EmoTune can return:

- primary emotion
- confidence
- all emotion scores
- top emotions
- Plutchik scores
- Plutchik dominant emotion
- top Plutchik emotions

This is useful for:

- admin/debugging
- analytics
- visualization
- explaining why a playlist was chosen

## 6. Recommendation Modes and Session Features

EmoTune currently supports these outcome modes:

- Match My Mood
- Calm Me Down
- Help Me Focus
- Lift Me Up
- Help Me Sleep

Each mode can reshape the original emotion profile before recommendation ranking.

Session features include:

- session length targets
- session phases
- track-based check-ins
- completion messaging
- progress tracking in seconds and tracks played
- session continuation or completion behavior

Taste controls include:

- familiarity: balanced, familiar, or discovery
- prefer instrumental
- train on this session or do not train on this session

## 7. Models Used in EmoTune

### 7.1 Runtime Emotion Model

The production classifier is BERT-first.

Main details:

- default model family: `bert-base-uncased`
- runtime loading through Hugging Face `transformers`
- runtime path normally points to a saved fine-tuned model directory
- if the saved model is missing or unusable, EmoTune falls back to a deterministic keyword-based classifier

The runtime classifier returns:

- predicted emotion
- confidence
- confidence band
- confidence margin
- fallback status
- top emotions
- Plutchik mapping

### 7.2 Fallback Classifier

When the BERT model is unavailable or confidence is too low, EmoTune uses a keyword-based fallback.

This fallback is useful for:

- local development
- model load failures
- uncertain predictions
- safer degraded behavior instead of a hard crash

### 7.3 Personalization / Ranking Model

EmoTune uses LightFM as a personalization and ranking layer after Spotify candidate retrieval.

LightFM works with:

- favorites
- listening sessions
- prompt history
- user preferences
- current emotional context

If LightFM is unavailable, the app falls back to a heuristic ranking path.

### 7.4 Secondary Mapping Model

EmoTune also uses a Plutchik mapping layer.

This is not a separate training model. It is a post-processing step that converts EmoTune emotion scores into a Plutchik-compatible profile for explainability and visualization.

## 8. Datasets Used

EmoTune's training pipeline supports a staged approach.

### 8.1 GoEmotions

Used as the base public dataset.

Purpose:

- broad general emotion understanding
- strong base stage before adapting to the EmoTune label system

### 8.2 dair-ai/emotion

Used as an optional intermediate adaptation dataset.

Purpose:

- extra public emotion coverage
- additional signal before final EmoTune fine-tuning

### 8.3 EmoTune Custom Dataset

This is the app-specific dataset in:

- `dataset/emotune_custom_dataset.csv`

Purpose:

- teach the final EmoTune label system
- cover app-specific emotions like `stressed`, `lonely`, `nostalgic`, `depressing`, and `mixed`
- serve as the final fine-tuning stage and final evaluation domain

### 8.4 In-Script Fallback Samples

The training pipeline also includes a small in-script fallback sample set in case the CSV cannot be loaded.

This is a safety fallback only and not the ideal long-term training source.

## 9. Training Pipeline

The intended BERT fine-tuning order is:

1. GoEmotions base fine-tune
2. optional `dair-ai/emotion` adaptation
3. EmoTune final fine-tune on the custom dataset

The final evaluation is reported on an EmoTune-only holdout set so the metrics reflect the app's real label schema.

Training outputs include:

- cleaned dataset quality report
- baseline experiment results
- trained BERT model directory
- staged training summary
- test prediction dump

## 10. Recommendation Pipeline

The recommendation pipeline combines multiple layers:

### 10.1 Emotion Understanding

- BERT-first prediction
- keyword fallback when needed
- supportive response generation

### 10.2 Retrieval

- Spotify user signals when available
- Spotify catalog search
- curated fallback logic

### 10.3 Ranking

- emotion alignment
- personalization score
- track metadata
- LightFM re-ranking
- heuristic fallbacks

### 10.4 Session Context

- outcome mode biasing
- check-in logic
- recovery flow for intense emotions
- taste controls

## 11. Recovery and Check-In Logic

EmoTune supports a special recovery flow for high-intensity moods, especially:

- sad
- stressed
- depressing
- angry

Behavior includes:

- track-count checkpoints
- feel-better prompts
- support emotion transitions such as moving toward calm or motivational states
- session-only check-ins for outcome-based listening modes

## 12. Authentication and Profile System

### 12.1 Sign-Up Data

The current sign-up flow now collects:

- display name
- email
- password
- password confirmation
- required terms/privacy acceptance
- optional mood-based personalization opt-in

### 12.2 User Data Stored

The user model currently stores:

- email
- username/display name
- terms acceptance timestamp
- personalization opt-in
- Spotify account linkage fields
- profile picture
- bio
- preferred artists
- timestamps

### 12.3 Profile Features

The profile area currently supports:

- theme switching
- preferred artists management
- editing display name
- changing password
- connecting and disconnecting Spotify
- turning mood-based personalization on or off

## 13. Main Stored App Data

The backend stores these important entities:

### 13.1 PromptHistory

Stores:

- user prompt text
- detected emotion
- confidence
- emotion scores
- AI response
- playlist data
- recommendation/session metadata
- session duration
- felt-better response

### 13.2 UserPreference

Stores:

- user
- emotion
- Spotify track ID
- track and artist names
- play count
- total listen time

### 13.3 FavoriteTrack

Stores:

- saved favorite songs
- Spotify IDs and metadata

### 13.4 ListeningSession

Stores:

- prompt-linked listening sessions
- listen duration
- completion status

## 14. Technology Stack

Main stack:

- Flutter
- Django REST Framework
- Simple JWT
- Spotify Web API
- Spotify App Remote
- PyTorch
- Hugging Face Transformers
- LightFM
- scikit-learn
- pandas
- NumPy

## 15. Important Project Areas

High-level project structure:

```text
backend/
  api/                  API logic, Spotify integration, ranking, session control
  ml/                   Runtime classifier and model loading
  users/                Auth, profile, history, favorites, listening data
dataset/                Custom dataset files
docs/                   Setup and label documentation
flutter_app/            Mobile/web client
ml_model/               Training, cleaning, inspection, and export scripts
```

## 16. Important Runtime and Training Controls

Examples of important environment/config controls:

- Spotify credentials and redirect URIs
- `ML_MODEL_PATH`
- emotion confidence thresholds
- LightFM enable/disable flags
- stage toggles for GoEmotions, dair-ai/emotion, and custom fine-tuning
- epoch counts
- batch size
- max sequence length
- repeat factor for the custom dataset

## 17. Current Strengths of the System

EmoTune is strongest when viewed as a layered system, not a single model.

Current strengths:

- custom 13-label emotion schema tailored to the app
- BERT + fallback safety path
- Spotify integration for real playable music
- LightFM re-ranking for personalization
- session-aware recommendation control
- explainable hybrid emotion output
- usable history, favorites, and profile system

## 18. Current Limitations and Notes

Important current notes:

- if the fine-tuned BERT model is not present, the runtime falls back to keywords
- LightFM is disabled on Windows by default because native runtime issues can crash the process on some setups
- Spotify development-mode allowlisting can block some accounts until they are added in the Spotify Developer Dashboard
- the app depends on Spotify credentials and correct redirect setup
- the Flutter side should still be validated on-device after larger UI changes

## 19. Summary

EmoTune currently combines:

- a custom emotion classifier
- staged BERT training
- fallback-safe prediction
- Spotify-based music retrieval
- LightFM personalization
- session-based recommendation control
- recovery and check-in logic
- explainability through Plutchik-compatible scores
- user data features such as history, favorites, preferences, and profile settings

In short, EmoTune is an emotion-aware, personalization-aware music recommendation platform built around both ML and product-level session logic.
