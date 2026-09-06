# EmoTune — System Overview

EmoTune is an emotion-aware music recommendation system. A user says how they
feel (in free text, or by picking an emotion), the backend classifies that
feeling into one of 13 emotion labels, and the system builds a Spotify playlist
that matches or gently steers that mood — then learns from what the user
actually listens to.

This document describes what the system *is* and how the pieces fit together.
For install and run instructions see [SETUP.md](SETUP.md).

---

## 1. The three parts

| Part | Stack | What it owns |
| --- | --- | --- |
| `flutter_app/` | Flutter (Dart), Provider state management | Mobile client: prompt entry, playback, favorites, history, profile, taste settings |
| `backend/` | Django 4.2 + Django REST Framework | Emotion classification, Spotify integration, ranking, persistence, admin panel |
| `ml_model/` | PyTorch / Transformers / scikit-learn | Offline training: BERT emotion model, ranker weight fitting, dataset tooling |

Auth between them is JWT (`djangorestframework-simplejwt`). Music comes from
the Spotify Web API (catalog + personalization) and plays through the Spotify
App Remote SDK on Android.

---

## 2. End-to-end request flow

```
 User types "I feel overwhelmed with everything I need to finish."
        │
        ▼
 [Flutter]  POST /api/analyze/  { text, taste_profile, session_length, check_in_frequency }
        │
        ▼
 [Django]  1. EmotionClassifier.predict()      → emotion + confidence + all 13 scores
           2. Plutchik mapper                  → secondary 8-emotion profile (explainability)
           3. Supportive text response         → EmotionResponseBuilder
           4. Candidate retrieval (Spotify)    → pool + live search + personalization + curated
           5. Ranking (picker_ranker)          → ordered playlist + one selected track
           6. Taste control                    → final say on ordering (familiar/balanced/discovery)
           7. Persist PromptHistory            → prompt, emotion, scores, playlist, picker data
        │
        ▼
 [Flutter]  Plays the selected track via Spotify App Remote, queues the rest,
            reports listen duration back to /api/users/listen-time/
```

Because step 4 can be slow, the response is **progressive/two-stage**:

- **Stage 1 (`initial`)** returns fast — a small candidate budget, one playable
  track, plus a signed `continuation_token`.
- **Stage 2 (`continuation`)** — the app calls `POST /api/recommendation-playlist/`
  with that token and gets the full playlist built with a larger budget.

Budgets and limits are configurable (`SPOTIFY_PROGRESSIVE_*`), and the token
expires after `RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS`.

---

## 3. Emotion analysis

**Label set (13, `backend/ml/emotion_labels.py`)** — the single source of truth
shared by the runtime classifier and the training script:

`happy, sad, angry, motivational, fear, depressing, surprising, stressed, calm,
lonely, romantic, nostalgic, mixed`

**Classifier (`backend/ml/emotion_classifier.py`)** is layered, and degrades
rather than fails:

1. **Fine-tuned BERT** loaded from `ML_MODEL_PATH`
   (`backend/ml/models/bert_emotion_model/`) — the primary path.
2. **GoEmotions model** (optional, `EMOTION_GOEMOTIONS_ENABLED`) mapped onto the
   13 labels via `GOEMOTIONS_LABEL_MAP`, used as a second opinion.
3. **Keyword scorer** (`KeywordEmotionScorer`) — deterministic fallback when no
   model loads or confidence is too low.

Every prediction reports *how* it was made, so the path is auditable:
`prediction_source`, `prediction_strategy`, `confidence_band`,
`confidence_margin`, `fallback_used`, `needs_review`. Thresholds come from
`EMOTION_HIGH_CONFIDENCE_THRESHOLD`, `EMOTION_MEDIUM_CONFIDENCE_THRESHOLD` and
`EMOTION_MIN_MARGIN_THRESHOLD`.

**Plutchik profile (`backend/ml/plutchik_mapper.py`)** derives a secondary
8-emotion profile (joy, trust, fear, surprise, sadness, disgust, anger,
anticipation) from the 13 label scores. It is heuristic and used for
visualization/explainability — it never replaces the primary prediction.

Users can also skip analysis entirely and pick an emotion tab, which hits
`POST /api/recommend-by-emotion/` and synthesizes a full-confidence result.

---

## 4. Music retrieval — the Spotify layer

`backend/api/spotify/` is split by responsibility (it used to be one monolithic
`spotify_service.py`):

| Module | Responsibility |
| --- | --- |
| `auth.py` | OAuth URL, code exchange, token refresh, client credentials, authenticated request helpers |
| `search.py` | Track/artist catalog search and result formatting |
| `recommendations.py` | Per-emotion query building, candidate blending, curated fallbacks, top-level orchestration |
| `personalization.py` | Per-user taste context (top tracks, saved tracks, recently played) and scoring against it |
| `playback.py` | Device transfer, prepare-playback, play/pause/seek/skip/volume |
| `pool.py` | The shared per-emotion candidate cache |
| `constants.py` | Emotion query profiles, curated seed data, API constants |
| `utils.py` | Pure stateless helpers shared by all of the above |

### The candidate pool ("waiting room")

`EmotionTrackPool` (the api app's only model) caches the **emotion-baseline**
half of a recommendation — what a search returns for an emotion with no
user-specific input. Rows are shared across users because they contain nothing
user-specific; per-user personalization still runs live on every request and is
blended on top.

Freshness has three bands:
- younger than `SPOTIFY_TRACK_POOL_FRESH_SECONDS` → served as is
- older, but under `SPOTIFY_TRACK_POOL_MAX_AGE_SECONDS` → still served (stale beats slow), flagged for refresh
- past max age → ignored; the request falls back to live search and self-heals the pool

Warm it with `python manage.py refresh_emotion_pools` (cron / systemd timer).
Every pool DB call is best-effort: a broken pool costs latency, never a request.

### Curated document list

`docs/music.md` holds a hand-curated English + Filipino track list per emotion.
It seeds the "Balanced" taste mode (see §6) and is referenced by
`MUSIC_PICKER_PLAYLIST_DOC`.

---

## 5. Ranking — which song actually plays

One ranker, behind one entry point (`music_picker.pick_playlist` in
`backend/api/music_picker.py`, which orchestrates and shapes the payload):

**`backend/api/picker_ranker.py` — the shipped ranker.** A feature-based linear
model: each candidate is scored as a weighted sum of signals the recommendation
engine already computed, so ranking a whole candidate set costs one dot product
per track — no model fitting, no native extension, no extra process memory.

Feature order (both scoring and training import it, so they cannot drift):

```
emotion_alignment, personalization, popularity, availability,
is_preferred, familiar_source, discovery_fit, instrumental_fit
```

The weights are **data, not code**. `ml_model/train_picker_ranker.py` fits them
offline from real listening outcomes and writes
`ml_model/artifacts/picker_weights.json` (`PICKER_RANKER_WEIGHTS_PATH`). With no
artifact on disk, the built-in defaults reproduce the previous hand-tuned blend,
so an untrained deployment ranks exactly as it did before.

LightFM was removed. The module presented a collaborative-filtering layer as the
ranker and the linear picker as its fallback, but it never actually ran: LightFM
publishes no wheels, its bundled Cython sources do not compile on Python 3.12,
and it was absent from `requirements.txt` for exactly that reason. Every
deployment took the fallback path, so the fallback was the product. Deleting it
removed ~700 lines of machinery (per-request corpus building, score blending,
feature hashing) that never executed. Results now report `used_fallback: False`
— under the old module that field meant "LightFM did not produce this ranking",
which was always true.

**`backend/api/llm_music_picker.py`** is the legacy network-LLM picker. It is
off by default (`LLM_MUSIC_PICKER_ENABLED=False`) and no longer wired into the
request path — the local rankers replaced it.

---

## 6. Session controls

`backend/api/recommendation_session.py` holds three user-facing controls.

**Outcome modes** — how the playlist should relate to the detected emotion. Two
modes ship, and the **classifier picks between them**; there is no user-facing
switch. Each mode carries target emotion weights, a default session length, a
check-in cadence, and its own prompt/completion copy:

| Mode | Intent | Routed emotions |
| --- | --- | --- |
| `match_mood` | Mirror the detected emotion | happy, surprising, motivational, calm, romantic, nostalgic, mixed |
| `calm_me_down` | Steer intensity toward something steadier | sad, stressed, depressing, angry, fear, lonely |

```
                 EMOTUNE
                    |
             BERT detects mood
                    |
          +---------+---------+
          |                   |
          v                   v
   MATCH MY MOOD         CALM ME DOWN
          |                   |
   happy                    sad
   surprising               stressed
   motivational             depressing
   calm                     angry
   romantic                 fear
   nostalgic                lonely
   mixed
```

`EMOTION_OUTCOME_MODES` holds the table and `resolve_outcome_mode(emotion,
requested)` applies it. An explicit `outcome_mode` in the request still wins,
which is what keeps a stage-2 continuation on the mode stage 1 committed to.
`mixed` is mirrored: it means the classifier could not commit, and steering on
that presumes more than the signal supports.

> **Known limit.** `calm_me_down` blends 58% toward its calm target
> (`target_weight`), which is not enough to overtake a detected emotion above
> roughly 0.7 confidence. At `sad = 0.8` the blend gives `sad 0.394` against
> `calm 0.361`, so sad still leads the recommendation lane — the strongest
> distress readings are the ones least steered. Raising `target_weight` is a
> therapeutic tuning decision, not a bug fix.

**Session plan** — session length in minutes plus a check-in cadence in tracks.
`build_session_plan` / `update_session_plan_progress` track progress and decide
when the app should ask how things are going.

**Taste profile** — persisted client-side (`RecommendationStudioProvider`,
`SharedPreferences`) and sent with every request:

- `familiarity`: `familiar` — favorites saved under this emotion lead, up to a
  quota, so unheard songs still get room; `discovery` — the static curated
  tracks are filtered out; `balanced` — the `docs/music.md` list for the emotion
  leads in document order, capped at half the playlist.
- `prefer_instrumental`: biases ranking toward instrumental candidates and skips
  the (vocal-pop) document list.
- `train_session`: when false, the session is excluded from personalization
  learning.

`_apply_taste_control` in `views.py` runs **after** ranking and enforces these
promises — ranking decides quality, taste control decides what the user was
promised.

**Recovery / feel-better loop** — for high-intensity sessions the app polls
`POST /api/feel-better/` with tracks played and duration. When a checkpoint is
reached the backend returns a prompt ("You've listened to N songs. Are you
feeling better right now?"); the answer goes to `POST /api/feel-better-response/`,
which can transition the playlist into a support phase.

---

## 7. Data model

**`api` app** — one model only:
- `EmotionTrackPool` — shared per-emotion candidate cache (see §4).

**`users` app** — everything user-facing:
- `User` (custom, email as `USERNAME_FIELD`) — profile, bio, avatar,
  `preferred_artists`, `personalization_opt_in`, `terms_accepted_at`, and the
  Spotify connection (id, access/refresh tokens, granted scopes, expiry).
- `UserPreference` — per `(user, emotion, track)` play count and total listen
  time; the adaptive personalization signal.
- `FavoriteTrack` — hearted tracks, tagged with the emotion they were hearted
  under, so "more familiar" can replay them for that emotion.
- `PromptHistory` — the central record: prompt text, detected emotion,
  confidence, all emotion scores, AI response, playlist data, `music_picker_data`
  (strategy, candidates, session plan, recovery plan), session duration, and the
  feel-better answer.
- `ListeningSession` — one row per playback, including short ones. Deliberate:
  a skip is the only negative example the ranker ever sees.

---

## 8. API surface

**Core** (`/api/`)
| Endpoint | Purpose |
| --- | --- |
| `POST /analyze/` | Text → emotion + response + playlist (stage 1) |
| `POST /recommend-by-emotion/` | Explicit emotion tab → playlist |
| `POST /recommendation-playlist/` | Continue a progressive request (stage 2) |
| `POST /feel-better/` | Should we show a recovery/check-in prompt? |
| `POST /feel-better-response/` | Record the answer, optionally transition the playlist |

**Spotify** (`/api/spotify/`)
`app-remote-config/`, `auth-url/`, `callback/`, `debug-status/`,
`prepare-playback/`, `player-control/`, `disconnect/`, `search-artists/`,
`search-tracks/`

**Users** (`/api/users/`)
`register/`, `login/`, `logout/`, `token/refresh/`, `profile/`,
`change-password/`, `update-artists/`, `favorites/`, `favorites/<track_id>/`,
`history/`, `emotion-stats/`, `listen-time/`

**Admin** — `/api/admin/dashboard/`, `/api/admin/users/`,
`/api/admin/users/<id>/` (all `IsAdminUser`), plus the HTML console at
`/admin-panel/` which is gated by Django's `@staff_member_required` session
check and mints a short-lived JWT for the page's API calls. `/` redirects there.

---

## 9. The Flutter client

Five tabs in `MainShell`: **Home** (prompt entry + analysis), **Favorites**,
**Recommendations** (emotion tabs), **History**, **Profile**.

- `providers/player_provider.dart` — the largest piece: playback state, queue
  management, progressive continuation, listen-time reporting.
- `providers/auth_provider.dart` — JWT session, token refresh.
- `providers/recommendation_studio_provider.dart` — session length, check-in
  frequency, familiarity, instrumental preference (persisted locally).
- `providers/spotify_availability_tracker.dart` — tracks which items are
  actually playable.
- `services/api_service.dart` — all HTTP, plus base-URL auto-resolution (it
  probes emulator vs. LAN addresses and caches what worked).
- `services/spotify_remote_service.dart` + `controllers/spotify_connection_controller.dart`
  — Spotify App Remote SDK bridge and connection lifecycle.

---

## 10. The ML workflow

**Datasets** (`dataset/`) — a custom labelled emotion corpus
(`emotune_custom_dataset.csv`, ~1.1k rows), a larger
`emotune_dataset_1200.csv`, cleaned variants with length/label metadata, plus
survey-collected rows.

**Emotion model** (`ml_model/train_bert.py`) — staged fine-tuning:
1. GoEmotions base fine-tune (`EMOTUNE_ENABLE_GOEMOTIONS`)
2. optional `dair-ai/emotion` adaptation (`EMOTUNE_ENABLE_DAIR_EMOTION`)
3. final fine-tune on the custom EmoTune dataset

Outputs to `backend/ml/models/bert_emotion_model/` with a
`training_results.json` summary. `train_baseline.py` provides classical
scikit-learn baselines for comparison; `inspect_dataset.py` writes a data
quality report.

**Ranker weights** (`ml_model/train_picker_ranker.py`) — fits the picker's
linear weights from real usage. Two label choices:
- `outcome` (default) — the candidate the user actually listened through. The
  only label carrying information the picker does not already have.
- `selection` — the candidate the picker chose. Measured as **degenerate**
  (the pick was candidate #0 in 164 of 167 prompts, because the stored candidate
  list is already ranked). Kept only so the leakage stays visible.

Splits are **by prompt, never by row**, and the artifact is written only if the
fitted weights beat the current defaults on held-out prompts.

`ml_model/export_music_picker_dataset.py` exports prompt-history rows as JSONL
for offline analysis.

---

## 11. Configuration

All configuration is environment-driven (see `.env.example`). Groups:

- `DJANGO_*` — secret key, debug, allowed hosts, HSTS/security headers
- `SPOTIFY_*` — credentials, redirect URIs, scopes, HTTP + recommendation budgets
- `SPOTIFY_PROGRESSIVE_*` — stage-1/stage-2 budgets and candidate limits
- `SPOTIFY_TRACK_POOL_*` — pool enable, target size, freshness bands, refresh budget
- `PICKER_RANKER_*` — enable flag, weights artifact path
- `EMOTION_*` — confidence/margin thresholds, top-emotion count, GoEmotions toggles
- `ML_MODEL_PATH`, `MUSIC_PICKER_PLAYLIST_DOC`, `RECOMMENDATION_CONTINUATION_MAX_AGE_SECONDS`

Never commit `.env`; treat `.env.example` as placeholders only. While the
Spotify app is in Development Mode, real accounts must be on the dashboard
allowlist or the API returns a structured `developer_allowlist_required` error.

---

## 12. Design principles visible in the code

- **Degrade, never fail.** Every layer has a fallback: BERT → GoEmotions →
  keywords; pool → live search → curated tracks; ranked playlist → arrival
  order. A broken cache or a missing model costs quality, not the
  request.
- **Always say how the answer was made.** Responses carry
  `prediction_source`, `prediction_strategy`, `tracks_source`,
  `music_picker.strategy`, `used_fallback`, `reason` — so any playlist can be
  traced back to the path that produced it.
- **Weights are data.** Hand-tuned defaults ship in code; trained weights arrive
  as an artifact and only replace the defaults if they win on held-out data.
- **One source of truth for shared vocabulary.** Emotion labels, feature order,
  and taste-profile reading each live in exactly one module that both the
  runtime and the training side import.
- **Ranking decides quality; taste control decides promises.** They are separate
  stages on purpose.

---

## 13. The Text Emotion Classification 150k corpus

`dataset/Text Emotion Classification 150k Dataset.csv` is two corpora
concatenated under one header, and the two halves are not of equal quality.
`ml_model/clean_text_emotion_dataset.py` normalizes it into EmoTune's schema and
writes `dataset/text_emotion_classification.cleaned.csv` plus
`ml_model/artifacts/text_emotion_cleaning_report.json`.

**152,499 rows in → 92,535 out.** What was dropped, and why:

| Dropped | Rows | Reason |
| --- | --- | --- |
| `sadness` class | 45,883 | Template-generated, see below |
| Empty category | 6,435 | No label |
| Duplicates | 4,387 | Same text after normalization |
| Over 60 words | 2,495 | Long-form articles, not mood statements |
| Misaligned columns | 671 | `original_text` and `cleaned_text` hold different events |
| Under 3 words | 88 | No usable signal |
| Low alphabetic ratio | 5 | Mojibake / symbol soup |

**Why the whole `sadness` class goes.** It is the largest class in the file
(30%) and it is machine-generated. Of 45,898 rows only 24,690 are unique, the
mean length is 5.3 words, and 60 sentence-final words cover 57% of the class,
each appearing 430–600 times (`sorrow` 598, `misery` 453, `depression` 449,
`anguish` 449). Real writing does not distribute like that. The rows read as
slot-filled frames — *"Biking pedals through somber."*, *"Museums remind me of
barren."*, *"My spirit pulses with unhappy."* The ~1.5k rows that are not
templates are mislabelled tweets (*"Anybody know a good place to book a show in
#Montreal"*), so there is no clean subset to rescue. Training on it would teach
the model that "sad" means broken grammar. `--keep-sadness` overrides this.

**Why 671 rows are misaligned.** In those rows `original_text` and
`cleaned_text` describe entirely different events — one a tweet, the other a
HappyDB entry — which means the two sources were merged row-wise incorrectly.
Since we cannot tell which text the label belongs to, the row is dropped.
Elsewhere `cleaned_text` is genuinely the better column (it fixes `youare` →
`you're`, `annd` → `and`), so the cleaner prefers it whenever the two agree.

**Label mapping.** HappyDB's categories are *topics of a happy moment*, not
emotions, so they map by topic: `achievement`/`exercise` → `motivational`,
`enjoy_the_moment`/`bonding` → `happy`, `nature` → `calm`. `affection` is split
by content — partner markers (spouse, fiancé, anniversary, date night…) →
`romantic`, everything else (family, children, friends) → `happy` — because
mapping the whole class to `romantic` would flood that label with family
content. The tweet-derived classes map directly: `joy` → `happy`, `anger` →
`angry`, `fear` → `fear`, `love` → `romantic`, `surprise` → `surprising`.

**What it cannot teach.** The cleaned corpus covers only 7 of the 13 labels.
There is no `sad`, `stressed`, `lonely`, `depressing`, `nostalgic` or `mixed`
data in it at all, and what remains is heavily skewed (43,890 `happy` against 66
`surprising`). It is therefore wired in as a **pre-training stage**, never the
final one — `_cap_per_class` flattens it to a roughly even ~11.4k-row, 7-label
stage, and the balanced EmoTune custom dataset still runs last to restore the
full schema.

### Where it sits in the training sequence

```
1. GoEmotions base fine-tune           EMOTUNE_ENABLE_GOEMOTIONS      (needs network)
2. dair-ai/emotion adaptation          EMOTUNE_ENABLE_DAIR_EMOTION    (off by default)
3. Text Emotion 150k pre-training      EMOTUNE_ENABLE_TEXT_EMOTION    (on by default)
4. EmoTune final fine-tune             EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE
```

Stages 1–3 buy the model real-world language; stage 4 is what makes all 13
labels reachable, which is why it always runs last. Rebuild the cleaned CSV with:

```bash
python ml_model/clean_text_emotion_dataset.py
```

### The final-stage dataset

The final fine-tune is the only stage covering all 13 labels, so it decides what
the deployed model can predict. Three labelled sources exist, and they are not
interchangeable:

| Source | Raw | Unique after cleaning | Labels |
| --- | --- | --- | --- |
| `emotune_custom_dataset.csv` | 1,100 | **164** (936 duplicates, 85%) | 13 |
| `emotune_dataset_1200.csv` | 1,200 | **1,200** (no duplicates) | 12 — no `mixed` |
| `surveyed_datasets.csv` | 41 | 38 | 13 (own label names) |

The pipeline defaulted to the custom file, which left ~12 examples per label and
a **13-row** holdout test set — too small to fine-tune on or to measure. The
1,200-row file cannot simply replace it either: with no `mixed` examples that
label becomes unpredictable.

`ml_model/build_emotune_training_set.py` combines all three into
`dataset/emotune_combined.csv` — **1,322 rows, all 13 labels**, deduplicated
across the union (the sources share near-identical rows differing only in
punctuation, which is why the custom file contributes 84 rather than 164). The
survey's older label names (`motivated`, `depressed`, `surprise`, `stress`) are
mapped onto the canonical schema rather than dropped as invalid.

```bash
python ml_model/build_emotune_training_set.py
EMOTUNE_DATASET_PATH=dataset/emotune_combined.csv python ml_model/train_bert.py
```

`mixed` remains thin at 15 rows — it exists in only one source. The trainer's
`WeightedTrainer` applies balanced class weights, so `mixed` carries roughly 7x
the loss weight of the other labels, but more real `mixed` examples is the only
actual fix.
