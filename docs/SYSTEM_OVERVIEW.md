# EmoTune — System Overview

EmoTune uses a BERT-based emotion classifier to identify the emotion expressed
in a student's text. The backend maps the predicted emotion to a fixed
collection of songs validated by a music therapist and retrieves all active
songs approved for that emotion. The Flutter application displays the complete
matching collection and allows the student to choose a song. The system does
not use a machine-learning model to rank or personalize songs.

EmoTune is designed to support emotional well-being through therapist-validated
music selection. It does not diagnose or treat mental-health conditions.

This document describes what the system *is* and how the pieces fit together.
For install and run instructions see [SETUP.md](SETUP.md).

---

## 1. The three parts

| Part | Stack | What it owns |
| --- | --- | --- |
| `flutter_app/` | Flutter (Dart), Provider state management | Mobile client: mood entry, the song list, in-app playback, favorites, history, profile |
| `backend/` | Django 4.2 + Django REST Framework | Crisis check, emotion classification, the therapist-approved song collection, Spotify auth/playback, persistence, admin panel |
| `ml_model/` | PyTorch / Transformers / scikit-learn | Offline training of the BERT emotion model and dataset tooling |

Auth between them is JWT (`djangorestframework-simplejwt`). The database is
MySQL 8 in Docker (SQLite for local development and tests). Spotify is used only
to *play* the approved songs (Spotify App Remote SDK on Android, with stored
track IDs) — never to choose them.

---

## 2. End-to-end request flow (data flow)

```
 Student types "I feel overwhelmed by all my school requirements."
        │
        ▼
 [Flutter]  POST /api/analyze/  { text, session_length_minutes?, check_in_frequency_tracks? }
        │
        ▼
 [Django]  1. Validate the text                → non-empty, at most 2,000 characters (else 400)
           2. Crisis-language check (safety.py) → crisis: support contacts, no songs; stop here
           3. EmotionClassifier.predict()      → one of 13 labels + confidence + all 13 scores
           4. Look up the Emotion record       → the label is the record's name (no LABEL_n mapping)
           5. Query the approved songs         → every active Song linked to that Emotion,
                                                  ordered by the therapist's list (EmotionSong.position)
           6. Concern check                    → may add a gentle check-in with support contacts
           7. Persist PromptHistory            → prompt, emotion, scores, the song list, session plan
        │
        ▼
 [Flutter]  Shows ALL returned songs (title, artist, artwork). The student picks one.
            Matched songs play in-app via Spotify; unmatched ones offer a Spotify search link.
            Playback progress goes to /api/users/listen-time/ (session progress, listening history).
```

The whole list comes back in one response — there is no second, "full playlist"
request any more, because the database lookup is instant and never calls
Spotify. If Spotify is unreachable the song details still display.

An unsupported label returns no songs and the message "No supported emotion was
identified." An emotion with no active songs returns an empty list and a message.

---

## 3. Emotion analysis

**Label set (13, `backend/ml/emotion_labels.py`)** — the single source of truth
shared by the runtime classifier, the training script and the `Emotion` table:

`happy, sad, angry, motivational, fear, depressing, surprising, stressed, calm,
lonely, romantic, nostalgic, mixed`

The trained model's `config.json` emits these names directly, so a prediction
maps to an `Emotion` row by name. Each row also has a `display_name` matching
the therapist's headings (Motivated, Scared, Depressed, Surprised, Mixed, ...).

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
`EMOTION_MIN_MARGIN_THRESHOLD`. Confidence is reported for diagnostics only; it
does not filter or reorder songs.

For the full decision path see [PREDICTION_PIPELINE.md](PREDICTION_PIPELINE.md).

**Plutchik profile (`backend/ml/plutchik_mapper.py`)** derives a secondary
8-emotion profile from the 13 label scores, for visualization only.

Students can also skip analysis and pick an emotion tab, which hits
`POST /api/recommend-by-emotion/` and returns that emotion's approved songs.

---

## 4. The song collection

The therapist-approved list in [`docs/music.md`](music.md) is the source of
truth: 13 emotions, 125 emotion–song approvals, 114 distinct songs (a song may
be approved for more than one emotion, e.g. "Leaves — Ben&Ben" for Depressed,
Calm and Stressed). It lives in three tables (see §7) and is seeded by data
migrations, never edited through an admin screen:

- `api/0008_seed_therapist_songs` — a frozen copy of `docs/music.md`. A migration
  must replay the same data forever, so it does not re-parse the document; a
  change to the collection is a new migration.
- `api/0009_store_remaining_spotify_matches` — Spotify matches found later.

Spotify's role is limited to stored metadata for playback. Each song's Spotify
track ID, URL, album and artwork were found **once, offline** (exact title +
artist match only, original recordings only) and stored on the row; no request
searches Spotify. 111 of the 114 songs are matched (one, Merry-Go-Round of Life, to the composer's
official re-recording because the original soundtrack is not on Spotify). An unmatched song is still listed — the app shows it
with a Spotify search link instead of a play button.

The `backend/api/spotify/` package now only handles OAuth (`auth.py`), in-app
playback (`playback.py`), the artist search used by the profile
(`search.py`), rate-limit cooldowns (`rate_limit.py`) and shared helpers.

---

## 5. No ranking, no personalization

The selection step is a deterministic database query:
`EmotionSong.objects.filter(emotion=..., song__is_active=True).order_by('position')`
(`songs_for_emotion` in `backend/api/models.py`). Nothing scores, filters or
reorders the result per user.

Removed in the 2026-10-10 refactor:

- **LightFM** — collaborative filtering. It never actually ran (no wheels for
  Python 3.12) and was already gone from the code before the refactor.
- **The linear picker** (`music_picker.py`, `picker_ranker.py`) and its offline
  weight training (`ml_model/train_picker_ranker.py`, the exported training set).
- **The LLM music picker** (`llm_music_picker.py`).
- **Spotify search-based retrieval** — per-emotion queries, the shared candidate
  pools and their refresher, personalization from a user's Spotify history, and
  the progressive "stage 1 / stage 2" playlist.
- **Taste controls** (More familiar / More discovery / Prefer instrumental),
  "Train on this session" and mood-based personalization.

---

## 6. Session controls and the feel-better loop

`backend/api/session_plan.py` holds the listening session.

**Session plan** — a session length in minutes plus a check-in cadence in
tracks. `build_session_plan` / `update_session_plan_progress` track progress
(settle → support → close) and decide when the app asks how things are going.

**Session modes** — the detected emotion picks one of two modes, which set the
check-in wording and cadence only. They no longer change which songs are served.

| Mode | Check-in | Emotions |
| --- | --- | --- |
| `match_mood` | every 5 tracks | happy, surprising, motivational, calm, romantic, nostalgic, mixed |
| `calm_me_down` | every 3 tracks | sad, stressed, depressing, angry, fear, lonely |

**Feel-better loop** — for a high-confidence sad, stressed, depressing or angry
reading, the app polls `POST /api/feel-better/` with tracks played and duration.
At a checkpoint the backend asks "Are you feeling better right now?"; the answer
goes to `POST /api/feel-better-response/`. A "yes" switches the list to a
support emotion's approved songs (calm, or motivational for angry) — again the
therapist's list, in order, never a ranked or searched one.

---

## 7. Data model (entity-relationship)

**`api` app**

```
Emotion (emotions)            Song (songs)                      EmotionSong (emotion_songs)
- id                          - id                              - id
- name (unique, BERT label)   - title                           - emotion_id  → Emotion
- display_name                - artist                          - song_id     → Song
- description                 - spotify_track_id (nullable)     - position (therapist order)
                              - spotify_url (nullable)          unique (emotion_id, song_id)
                              - album, image, duration_ms
                              - is_active
                              unique (title, artist)

Emotion 1 ──< EmotionSong >── 1 Song      (many-to-many through EmotionSong)
```

Also in `api`: `SupportResource` (crisis/support contacts) and `SupportEvent`
(counts of safety-check hits; stores no text and no user).

**`users` app**
- `User` (custom, email as `USERNAME_FIELD`) — display name, bio, avatar,
  `preferred_artists`, `terms_accepted_at`, and the Spotify connection (id,
  tokens, granted scopes, expiry).
- `FavoriteTrack` — hearted tracks, tagged with the emotion they were hearted under.
- `PromptHistory` — prompt text, detected emotion, confidence, all scores, AI
  response, the song list shown, session/recovery plan, session duration, and the
  feel-better answer.
- `ListeningSession` — one row per playback (listening history).

---

## 8. API surface

**Core** (`/api/`)
| Endpoint | Purpose |
| --- | --- |
| `POST /analyze/` | Text → crisis check → emotion → all approved songs + `total` |
| `POST /recommend-by-emotion/` | Emotion tab → that emotion's approved songs |
| `POST /feel-better/` | Should we show a check-in prompt? |
| `POST /feel-better-response/` | Record the answer; a "yes" can switch to the support emotion's songs |
| `GET /support-resources/` | Verified support contacts |

`/analyze/` response (abridged): `emotion`, `emotion_info {id, name,
display_name}`, `confidence`, `all_scores`, `top_emotions`, `ai_response`,
`session_plan`, `tracks[]`, `total`, `history_id`, plus `risk_level` /
`support_check_in` / `crisis` fields when the safety checks fire. Each track:
`id` (Spotify ID, or `song-<id>` when unmatched), `name`, `artist`, `album`,
`image`, `uri`, `spotify_url`, `duration_ms`, `song_id`, `position`, `playable`.

**Spotify** (`/api/spotify/`) — `app-remote-config/`, `auth-url/`, `callback/`,
`debug-status/`, `prepare-playback/`, `player-control/`, `disconnect/`,
`search-artists/`

**Users** (`/api/users/`) — `register/`, `login/`, `logout/`, `token/refresh/`,
`profile/`, `change-password/`, `password-reset/…`, `update-artists/`,
`favorites/`, `favorites/<track_id>/`, `history/`, `emotion-stats/`, `listen-time/`

**Admin** — `/api/admin/dashboard/`, `/api/admin/users/`,
`/api/admin/users/<id>/` (all `IsAdminUser`), plus the HTML console at
`/admin-panel/`, gated by Django's `@staff_member_required`.

---

## 9. The Flutter client

Five tabs in `MainShell`: **Home** (mood entry + analysis), **Favorites**,
**Recommendations** (emotion tabs), **History**, **Profile**. The app displays
every song the server returns, in the server's order, and calculates no scores.

- `providers/player_provider.dart` — playback state, queue, listen-time reporting.
- `providers/auth_provider.dart` — JWT session, token refresh.
- `services/api_service.dart` — all HTTP, plus base-URL auto-resolution.
- `services/spotify_remote_service.dart` + `controllers/spotify_connection_controller.dart`
  — Spotify App Remote SDK bridge and connection lifecycle.

---

## 10. The ML workflow

Machine learning in EmoTune is the emotion classifier only.

**Datasets** (`dataset/`) — the custom labelled emotion corpus and the cleaned
public corpora described in §13.

**Emotion model** (`ml_model/train_bert.py`) — staged fine-tuning (GoEmotions,
optional dair-ai/emotion, Text Emotion 150k pre-training, then the EmoTune
final stage), output to `backend/ml/models/bert_emotion_model/` with a
`training_results.json` summary. `train_baseline.py` provides scikit-learn
baselines; `compare_models.py` puts candidate models side by side for human
review before one is promoted.

**Evaluation.** BERT classification performance is evaluated separately from
the song mapping. The mapping is deterministic and is checked by tests (every
active song for the emotion, nothing from another emotion, inactive songs
excluded, therapist order). Therapist approval validates the song collection;
it does not by itself establish clinical effectiveness.

---

## 11. Configuration

All configuration is environment-driven (see `.env.example`). Groups:

- `DJANGO_*` — secret key, debug, allowed hosts, HSTS/security headers
- `DJANGO_DB_ENGINE`, `MYSQL_*` — MySQL in Docker; SQLite when unset
- `SPOTIFY_*` — credentials, redirect URIs, scopes, HTTP timeout
- `EMOTION_*` — confidence/margin thresholds, top-emotion count, GoEmotions toggles
- `ML_MODEL_PATH`, `CRISIS_HOTLINE_TEXT`, `THROTTLE_*`, `DRF_NUM_PROXIES`

Never commit `.env`; treat `.env.example` as placeholders only. While the
Spotify app is in Development Mode, real accounts must be on the dashboard
allowlist or the API returns a structured `developer_allowlist_required` error.

---

## 12. Design principles visible in the code

- **The approved list is the source of truth.** Songs come from the database
  mapping the therapist validated; Spotify never decides eligibility.
- **Deterministic and complete.** The same emotion always returns the same full
  list in the same order — the student chooses, not an algorithm.
- **Degrade, never fail.** BERT → GoEmotions → keywords; an unmatched song is
  still shown; an unreachable Spotify does not hide song details.
- **Always say how the answer was made.** Responses carry `prediction_source`,
  `prediction_strategy` and `tracks_source: therapist_list`.
- **One source of truth for shared vocabulary.** Emotion labels live in one
  module shared by the runtime, the training side and the `Emotion` table.

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
