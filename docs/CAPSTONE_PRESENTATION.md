# EmoTune — Capstone Presentation Brief

Everything the team needs to present EmoTune: what the system is, how the model
was built and how well it performs, every user-facing feature, and every safety
mechanism — plus the known limitations the panel is likely to probe.

All numbers below were read from the code and from the deployed model's own
artifacts on **2026-09-24**, not copied from older docs. Where an older doc
disagrees, this file says so.

> **Do not present the numbers in `docs/MODEL_TRAINING_RESULTS.md`.** That file
> describes a GoEmotions-based run on 26,000 samples with 79.5% accuracy. It does
> not match the model actually deployed in `backend/ml/models/bert_emotion_model/`
> (see §3). Use the figures in this document, which come from that model's
> `training_results.json`.

---

## Contents

1. [The pitch](#1-the-pitch)
2. [Architecture](#2-architecture)
3. [The emotion model](#3-the-emotion-model)
4. [How a prediction is made at runtime](#4-how-a-prediction-is-made-at-runtime)
5. [Music recommendation](#5-music-recommendation)
6. [The therapeutic design](#6-the-therapeutic-design)
7. [User-facing features](#7-user-facing-features)
8. [Safety functions](#8-safety-functions)
9. [Testing and QA](#9-testing-and-qa)
10. [Known limitations — say these before the panel does](#10-known-limitations--say-these-before-the-panel-does)
11. [Suggested slide outline and demo script](#11-suggested-slide-outline-and-demo-script)
12. [Likely panel questions](#12-likely-panel-questions)

---

## 1. The pitch

**Problem.** People already use music to regulate their mood, but streaming apps
recommend by listening history and genre, not by how the listener feels right
now — and they have no notion of whether a playlist is helping or making things
worse.

**EmoTune.** A mobile app where the user types how they feel (English or Taglish;
Tagalog support is still weak — §10.4). A fine-tuned BERT model classifies the feeling into one of **13
emotions**, the backend builds a Spotify playlist grounded in music-therapy
principles (the **iso-principle**: meet the mood, then gently shift it), and the
app checks in during the session to ask whether it is helping.

**What makes it more than a mood-to-genre lookup:**

- A domain-trained emotion model with an auditable fallback chain.
- A therapy-informed session arc that de-escalates distressing emotions instead
  of looping on them.
- A crisis-language safety net that stops the app from answering a crisis with a
  playlist.
- A ranker that learns from what users actually finish listening to.

---

## 2. Architecture

| Part | Stack | Responsibility |
| --- | --- | --- |
| `flutter_app/` | Flutter (Dart), Provider | Mobile client: mood entry, playback, favorites, history, profile, session controls |
| `backend/` | Django 4.2 + Django REST Framework, SimpleJWT | Emotion classification, crisis check, Spotify integration, ranking, persistence, admin |
| `ml_model/` | PyTorch, Hugging Face Transformers, scikit-learn | Offline training: BERT model, dataset cleaning, ranker weight fitting, baselines |
| External | Spotify Web API + Spotify App Remote SDK | Music catalog, personalization, playback on the device |

### End-to-end request flow

```
User: "I feel overwhelmed with everything I need to finish."
   │
   ▼
Flutter ── POST /api/analyze/ { text, taste_profile, session_length } ──►
   │
Django:
   0. Crisis-language check (safety.py) ── match? ──► support message, NO music
   1. Emotion classifier  → emotion + confidence + all 13 scores
   2. Plutchik mapper     → 8-emotion profile (explainability only)
   3. Outcome routing     → match_mood or calm_me_down
   4. Supportive response text
   5. Candidate retrieval → shared pool + live Spotify search + personalization + curated list
   6. Linear ranker       → ordered playlist + one selected track
   7. Taste control       → enforce familiar / balanced / discovery promises
   8. Save PromptHistory
   │
   ▼
Flutter plays the first track immediately, then fetches the full playlist
(POST /api/recommendation-playlist/ with a signed continuation token),
reports listen time, and shows check-in prompts.
```

**Progressive loading.** Stage 1 returns one playable track quickly; stage 2
builds the full playlist with a bigger time budget. The continuation token is
**signed** (`django.core.signing`) and expires, so a client cannot tamper with
the emotion or mode between stages.

---

## 3. The emotion model

### 3.1 The label set (13 emotions)

Single source of truth: `backend/ml/emotion_labels.py`, shared by training and
runtime so they cannot drift.

| Label | Covers |
| --- | --- |
| happy | joy, excitement, celebration, gratitude |
| sad | grief, disappointment, heartbreak, loss |
| angry | frustration, irritation, rage, resentment |
| motivational | ambition, confidence, drive, determination |
| fear | anxiety, nervousness, dread |
| depressing | emptiness, hopelessness, numbness, despair |
| surprising | shock, amazement, unexpected events |
| stressed | overload, pressure, burnout, tension |
| calm | peace, stillness, relaxation, contentment |
| lonely | isolation, longing, disconnection |
| romantic | affection, intimacy, love, attraction |
| nostalgic | memories, throwbacks, looking back |
| mixed | overlapping or unclear emotional states |

### 3.2 Model

- **Architecture:** `bert-base-uncased`, `BertForSequenceClassification`,
  single-label, 13 outputs (12 layers, 768 hidden, ~110M parameters, ~438 MB).
- **Max input:** 128 tokens. Learning rate 2e-5, warmup 0.1, batch size 16, seed 42.

### 3.3 Data

| Dataset | Raw rows | Used | Role |
| --- | --- | --- | --- |
| Text Emotion Classification 150k (HappyDB + tweets) | 152,499 | 92,535 after cleaning, capped to ~11.4k balanced | **Stage 1 pre-training** — real-world language, 7 labels only |
| `emotune_custom_dataset.csv` | 1,100 | 164 unique (85% duplicates) | Merged into combined set |
| `emotune_dataset_1200.csv` | 1,200 | 1,200 | Merged into combined set (no `mixed`) |
| `surveyed_datasets.csv` (team survey) | 41 | 38 | Merged into combined set |
| **`emotune_combined.csv`** | — | **1,322 rows, all 13 labels** | **Final fine-tune** |

**Data cleaning worth presenting** (it shows rigor):

- The whole `sadness` class of the 150k corpus (45,883 rows, 30% of the file) was
  **dropped as machine-generated**: only 54% unique, mean length 5.3 words, and 60
  sentence-final words covering 57% of the class ("Museums remind me of
  barren."). Training on it would teach the model that "sad" means broken grammar.
- 671 rows dropped where the two text columns described different events (a
  row-wise merge error in the source).
- HappyDB topic categories mapped to emotions by meaning (`achievement` →
  motivational, `nature` → calm; `affection` split into romantic vs. happy by
  partner keywords).
- The survey's older label names (`motivated`, `depressed`, `stress`) mapped
  onto the canonical schema rather than thrown away.

Full cleaning log: `ml_model/artifacts/text_emotion_cleaning_report.json`.

### 3.4 Training pipeline (two stages, CPU-only)

```
Stage 1  Text Emotion 150k pre-training   → eval weighted F1 0.743 (checkpoint 304)
Stage 2  EmoTune final fine-tune (all 13) → deployed model
         warm-started from stage 1, 4 epochs, custom data repeated ×3
         3,369 training examples · 99 validation · 100 test
         ~2.5 h on a 4-thread CPU (~19 s/step)
```

The final stage uses **class-weighted loss** — `mixed` has only 15 real rows, so
it carries ~6.6× the loss weight of other labels.

### 3.5 Results (deployed model, held-out test set, n = 100)

| Metric | Score |
| --- | --- |
| **Accuracy** | **85.0%** |
| **Weighted F1** | **0.852** |
| Macro F1 | 0.838 |
| Weighted precision | 0.875 |
| Validation weighted F1 | 0.851 (n = 99) |

| Emotion | Precision | Recall | F1 |
| --- | --- | --- | --- |
| nostalgic | 1.00 | 1.00 | 1.00 |
| angry | 0.90 | 1.00 | 0.95 |
| surprising | 1.00 | 0.89 | 0.94 |
| happy | 1.00 | 0.88 | 0.93 |
| romantic | 1.00 | 0.88 | 0.93 |
| fear | 0.80 | 1.00 | 0.89 |
| calm | 1.00 | 0.75 | 0.86 |
| lonely | 1.00 | 0.75 | 0.86 |
| sad | 0.64 | 1.00 | 0.78 |
| motivational | 0.75 | 0.75 | 0.75 |
| depressing | 0.83 | 0.63 | 0.71 |
| mixed | 0.50 | 1.00 | 0.67 *(1 test example)* |
| stressed | 0.63 | 0.63 | 0.63 |

**How to read this honestly:**

- The weakest labels are **stressed, depressing and sad** — and they are
  confused with each other. `sad` has perfect recall but 0.64 precision: other
  negative states get pulled into `sad`. For music selection this is a soft
  error (all three route to the same de-escalating mode, §6).
- The test set is **100 rows, ~8 per label** — one misclassification moves a
  label's F1 by ~0.1. `mixed` has **one** test example; its score means nothing.
- **Baseline for comparison:** TF-IDF + logistic regression on the original
  164-row custom set scored 52.9% accuracy / 0.50 weighted F1
  (`ml_model/artifacts/baseline_results.json`). It was a smaller, different
  split, so present it as "the classical baseline was far weaker," not as a
  controlled +32-point gain.

---

## 4. How a prediction is made at runtime

`backend/ml/emotion_classifier.py` layers three predictors and **degrades rather
than fails**:

```
                  text
                   │
         ┌─────────▼─────────┐
         │ Fine-tuned BERT   │── confidence ≥ 0.68 ──────► bert_high_confidence
         │ (primary)         │── ≥ 0.45 & margin ≥ 0.12 ─► bert_medium_confidence
         └─────────┬─────────┘
                   │ low confidence, or BERT error
         ┌─────────▼─────────┐
         │ GoEmotions RoBERTa│── usable ─────────────────► goemotions_*_fallback
         │ (second opinion,  │   (SamLowe/roberta-base-go_emotions,
         │  28 → 13 mapping) │    local only, 28 labels mapped to 13)
         └─────────┬─────────┘
                   │
         ┌─────────▼─────────┐
         │ Keyword scorer    │──────────────────────────► keyword_fallback
         └───────────────────┘
```

Every response says how it was produced: `prediction_source`,
`prediction_strategy`, `confidence_band`, `confidence_margin`,
`prediction_fallback_used`, `needs_review`. Any playlist can be traced back to
the path that made it.

**Plutchik profile** (`backend/ml/plutchik_mapper.py`): the 13 scores are also
projected onto Plutchik's 8 basic emotions (joy, trust, fear, surprise, sadness,
disgust, anger, anticipation) for visualization. It is a heuristic for
explainability and never overrides the primary prediction.

**Emotion tabs:** users who already know their mood can skip the text and tap
an emotion (`POST /api/recommend-by-emotion/`).

---

## 5. Music recommendation

### 5.1 Candidate sources

1. **Shared emotion pool** (`EmotionTrackPool`) — a per-emotion cache of what
   Spotify returns for that emotion with no personal input. Shared across users
   because it contains nothing personal. Fresh < 6 h, stale-but-served until the
   max age, then ignored and rebuilt. Warmed by
   `python manage.py refresh_emotion_pools`.
2. **Live Spotify search** — per-emotion query profiles (keywords + genres) in
   `backend/api/spotify/constants.py`, plus preferred artists.
3. **Personalization** — the user's Spotify top tracks, saved tracks and recently
   played (only if they connected Spotify and opted in).
4. **Curated list** — `docs/music.md`, a hand-picked English + Filipino list per
   emotion, reviewed against content-safety criteria (§8.3).
5. **Curated fallbacks** — Spotify playlists returned when the API is
   unavailable, so the user always gets something playable.

### 5.2 Ranking — the linear picker

`backend/api/picker_ranker.py` scores each candidate as a weighted sum of 8
features:

```
emotion_alignment, personalization, popularity, availability,
is_preferred, familiar_source, discovery_fit, instrumental_fit
```

- **Weights are data, not code.** `ml_model/train_picker_ranker.py` fits them
  offline from real listening outcomes (label = the track the user actually
  listened through). The new weights are written only if they beat the defaults
  on held-out prompts, split by prompt (never by row) to prevent leakage.
- There are **190** logged prompt rows so far
  (`ml_model/artifacts/music_picker_training.jsonl`). No trained weights file is
  deployed yet, so the app currently ranks with the hand-tuned defaults.
- **Why not collaborative filtering?** LightFM was evaluated and removed: it does
  not build on Python 3.12, so it never actually ran. The linear model is fast,
  explainable, and trainable with the data a capstone can collect.

### 5.3 Taste control (runs after ranking)

- **Balanced** — the curated `docs/music.md` list for the emotion leads, capped at
  half the playlist.
- **More familiar** — favorites saved under this emotion lead, with room left for
  new songs.
- **More discovery** — curated staples filtered out.
- **Prefer instrumental** — biases toward instrumental tracks and skips the
  (vocal) curated list.

"Ranking decides quality; taste control decides what the user was promised."

### 5.4 Optional LLM search planner

An LLM (Gemini-configurable) can suggest extra Spotify search queries from the
user's own words. It is **strictly additive and off by default**
(`LLM_MUSIC_PICKER_ENABLED=false`): its queries are appended, the ranker still
decides the order, and any failure or timeout silently falls back to the
built-in queries.

---

## 6. The therapeutic design

Rationale and citations: `docs/music_therapy_guidelines.md`.

### 6.1 Frameworks

| Framework | How EmoTune uses it |
| --- | --- |
| **Iso-principle** (Altshuler, 1944) | Match the current mood first, then shift toward the target state |
| **Circumplex model** (Russell, 1980) | Valence × arousal placement of each emotion |
| **GEMS** (Zentner et al., 2008) | Music-specific vocabulary for nostalgic / romantic / calm |
| **Mood-regulation strategies** (Saarikallio & Erkkilä, 2007) | Each emotion names its goal: Solace, Discharge, Revival, Diversion… |
| **Anger & extreme music** (Sharman & Dingle, 2015) | Matching anger is fine *if the session then moves toward calm* — the risk is dwelling, not matching |

### 6.2 Outcome routing — chosen by the classifier, not the user

| Mode | Intent | Emotions |
| --- | --- | --- |
| **Match my mood** | Mirror and sustain | happy, surprising, motivational, calm, romantic, nostalgic, mixed |
| **Calm me down** | Meet, then de-escalate | sad, stressed, depressing, angry, fear, lonely |

The manual mode switch was **removed from the app on purpose**: a distressed
user should not be able to opt into a session that only amplifies the feeling.

### 6.3 The iso-principle arc

`calm_me_down` moves through three phases as the user listens:

| Phase | Pull toward calm | Intent |
| --- | --- | --- |
| settle | 0.40 | Meet the listener where they are |
| support | 0.58 | Transition |
| close | 0.78 | Arrive at a steadier state |

| Reading | settle | support | close |
| --- | --- | --- | --- |
| angry 0.9 | angry | calm | calm |
| lonely 0.9 | lonely | calm | calm |
| sad 0.9 | sad | sad | calm |

**Safety property:** emotions with no seat in the calm target (angry, depressing,
lonely) are discounted twice, so even a 0.99-confidence `angry` reading can lead
only at the start and can never keep the playlist on aggressive content. Tested
up to 0.99 confidence in `api/test_outcome_routing.py`.

`settle` is deliberately 0.40, not 0 — a pure match would hand someone who said
they feel hopeless a playlist that only deepens it.

### 6.4 Check-ins ("Are you feeling better?")

A session has a length (Auto / 15 / 20 / 45 min) and a check-in rhythm (every 3
tracks for calm-me-down, 5 for match-my-mood). At a checkpoint the app asks; the
answer (`/api/feel-better-response/`) can move the playlist to the next phase or
close the session. The answer is also stored as outcome data.

---

## 7. User-facing features

| Area | Features |
| --- | --- |
| **Onboarding / auth** | Welcome & splash screens, register (terms acceptance required), login, logout, **forgot password with a 6-digit email code**, change password, password strength meter |
| **Home** | Mood composer (free text, English/Taglish), detected emotion + confidence chip, supportive message, instant first track, progressive full playlist, empty state and header |
| **Session studio** | Session length, taste control (Balanced / More familiar / More discovery), prefer instrumental, "train on this session" toggle |
| **Recommendations tab** | Pick an emotion directly and get a playlist |
| **Player** | Spotify App Remote playback, mini player + full player, queue, skip/seek/volume, playability tracking |
| **Favorites** | Heart a track; tagged with the emotion it was saved under so "More familiar" can bring it back |
| **History** | Past prompts, detected emotions, playlists, emotion statistics |
| **Profile** | Bio, avatar, preferred artists, Spotify connect/disconnect, personalization opt-in, theme |
| **Admin** | Staff dashboard and user management (`/admin-panel/`, admin-only APIs) |
| **Design** | Unified EmoTune dark design system across all screens |

---

## 8. Safety functions

Group these into three stories for the panel: **protecting the person**,
**protecting what they hear**, **protecting their data**.

### 8.1 Protecting the person — crisis-language detection

`backend/api/safety.py` runs **before** the emotion model on every free-text
entry point (`/analyze/` and `/recommend-by-emotion/` with text).

- On a match, the request is **short-circuited**: no emotion classification, no
  playlist, no autoplay. The response carries `crisis: true` and a support
  message telling the user to contact emergency services, a crisis line, a
  professional or someone they trust — *"You deserve support from a real person,
  not just music."*
- The Flutter home screen switches to a dedicated state ("We'd rather check in
  than play a song"), shows no tracks and does not autoplay.
- English **and Filipino/Taglish** phrases (e.g. "magpapakamatay", "ayoko na
  mabuhay", "gusto ko nang mamatay").
- Designed around the principle that **false negatives are worse than false
  positives**; phrases are multi-word so casual speech ("dying laughing") does
  not trigger it.
- A region-specific hotline is appended through `CRISIS_HOTLINE_TEXT`. It is
  deliberately empty by default — shipping an outdated number is worse than
  none — and must be set to a verified line before real use.
- Every detection is logged server-side.
- 9 dedicated tests (`api/test_crisis_safety.py`).

**Why a separate layer:** an emotion label (even `depressing`) is not a reliable
proxy for self-harm risk. Risk is judged on the text itself.

> **Current gap — present this honestly** (see §10): in QA on 2026-09-23 the
> phrase list caught **11 of 36** realistic crisis messages. "I have a plan to
> overdose tonight" was classified `stressed` and received calming music. This
> is the top open item.

### 8.2 Protecting the person — session design

- **Automatic de-escalation** for the six distressing emotions (§6.2); the user
  cannot switch a distressed session into amplification.
- **Bounded high-arousal matching:** angry/depressing/lonely can never hold the
  top slot for long, even at maximum confidence (§6.3).
- **Check-ins** keep a human in the loop on whether the session is helping.
- **Supportive text is validating, not dismissive** — no forced cheerfulness for
  sad states, consistent with grief-support practice.

### 8.3 Protecting what they hear — content safety for curated music

Every list in `docs/music.md` is reviewed against five criteria. A track is
disqualified if it:

1. Matches the literal word instead of the emotional need (the old `fear` list
   was horror songs — *Thriller*, *Disturbia* — for an anxious listener; replaced
   with grounding music).
2. References or romanticizes suicide, self-harm or wanting to disappear.
3. Normalizes a harmful coping mechanism (drinking songs removed from `stressed`).
4. Glorifies violence (a gun-centred track removed from `angry`).
5. Escalates arousal in a de-escalation category.

Six replacements were made (e.g. *I Know It's Over* → *Lean On Me* in
`depressing`); several Filipino tracks are flagged for a human lyric check rather
than changed unilaterally.

### 8.4 Protecting their data — privacy and security

| Control | Detail |
| --- | --- |
| **Authentication** | JWT; access tokens 60 min, refresh tokens 30 days with **rotation + blacklisting** (logout actually revokes) |
| **Rate limiting** | Login (20/min per IP, 10/min per email), register (10/h), password change (10/h), password reset request/verify throttled per IP and per email |
| **Password reset** | 6-digit code generated with `secrets`, **only the hash is stored**, 10-minute expiry, max 5 attempts, response never reveals whether an email has an account |
| **Passwords** | Django's hashed storage; similarity, common-password and numeric-only validators |
| **Authorization** | Every personal endpoint requires login; users can only reach their own history and sessions; admin APIs require staff |
| **Consent** | Terms must be accepted at registration (timestamp stored); personalization opt-in; per-session "train on this session" toggle excludes a session from learning |
| **Spotify** | OAuth with a signed state parameter; tokens refreshed server-side; disconnect endpoint; the shared pool stores no personal data |
| **Transport / headers** | In production: HTTPS redirect, HSTS (1 year), secure + HttpOnly + SameSite cookies, `X-Frame-Options: DENY`, nosniff, strict referrer policy |
| **CORS** | Open only in debug; startup refuses the unsafe "all origins + credentials" combination in production |
| **Tamper-proofing** | Continuation tokens are signed and expire |
| **Resilience** | Every layer degrades instead of failing: BERT → GoEmotions → keywords; pool → live search → curated fallbacks |

---

## 9. Testing and QA

**Automated tests (run 2026-09-23):**

| Suite | Result |
| --- | --- |
| Backend (Django) — 273 tests | 272 pass. The 1 failure is a test-configuration issue (the local `.env` changes a cache setting the test assumes), not a product bug |
| Flutter widget tests — 36 tests | 33 pass. The 3 failures are out-of-date tests written for the old session-controls labels before the design-system update |
| `flutter analyze` | No issues |
| Django system + migration checks | Clean |

Test coverage by area:

| Area | Tests |
| --- | --- |
| Core API, recommendations, pool (`api/tests.py`) | 111 |
| Taste control | 33 |
| Outcome routing / iso arc | 27 |
| Picker ranker + training | 25 |
| Listening-session logging | 14 |
| Session length | 11 |
| Taste signals | 11 |
| Users / auth | 10 |
| **Crisis safety** | **9** |
| **Password reset** | **9** |
| LLM search plan | 8 |
| Spotify failure classification | 5 |

**Manual live-API QA** confirmed: correct 401/403 handling, a user cannot reach
another user's session (404), tampered continuation tokens rejected, the
password reset does not reveal accounts, and the full playlist arrives about 4 s
after the first track.

---

## 10. Known limitations — say these before the panel does

Naming these yourselves shows maturity. Ordered by severity.

1. **Crisis detection is phrase-based and misses most indirect phrasing.** QA:
   11/36 caught. Missed examples include "i wanna die", "kms", "I have a plan to
   overdose tonight", "Everyone would be better off without me", "sana mamatay na
   lang ako". **Planned fix:** a second, meaning-based check (a classifier or LLM
   screen) alongside the phrase list, with a clinician reviewing the phrase set.
2. **No crisis hotline configured yet** (`CRISIS_HOTLINE_TEXT` empty) — needs a
   verified Philippine line (to be confirmed with a professional, not guessed).
3. **Small test set.** 100 test rows, 1 `mixed` example. Results are indicative,
   not definitive. More real, especially `mixed` and Filipino, data is the fix.
4. **Filipino / Tagalog input is weak.** The test set is mostly English. In a
   spot check on 2026-09-24, 5 of 7 Tagalog sentences were misclassified, most
   often as `stressed` — e.g. *"Ang lungkot ko, iniwan ako ng jowa ko"* (sad) →
   `stressed`, *"Mag-isa lang ako palagi, walang kausap"* (lonely) → `stressed`.
   Taglish that contains English emotion words ("stressed na ako") works well.
   Because most of these errors land on a calm-me-down emotion, the user still
   gets a de-escalating session, but the label and message are wrong. Fix: more
   labelled Filipino data in the final stage, and a Filipino-only test split.
5. **stressed / sad / depressing confusion** — the weakest labels. Mitigated
   because all three route to the same de-escalating mode.
6. **No explicit-content filter** on live Spotify search results. Only the
   curated seed tracks are reviewed; `explicit` flags are not checked.
7. **Spotify rate limiting.** When Spotify returns 429, the app keeps sending
   searches instead of backing off, and users get generic fallback playlists.
   Spotify Development Mode also limits the app to allow-listed accounts.
8. **Ranker not yet trained** on real outcomes — runs on hand-tuned defaults until
   enough listening data is collected (190 rows logged so far).
9. **The iso arc advances only at check-ins,** not within a single playlist; a
   user who never answers a check-in stays in the "settle" phase.
10. **Minor:** the feel-better endpoints return HTTP 500 on a non-numeric
   `history_id` (should be 400); password minimum is 6 characters; Spotify tokens
   are stored unencrypted in the database; no maximum prompt length.
11. **Not a clinical tool.** EmoTune is a wellbeing aid, not therapy or diagnosis.
    Therapeutic judgment calls (which songs validate sadness without
    romanticizing despair, when to escalate) need clinician review.

### Questions to bring to the music-therapist interview

- Which crisis phrasings (English and Filipino) should always trigger the safety
  response? Is a phrase list defensible at all, or should it always be paired
  with a model?
- Which Philippine crisis line should the app show, and how is it kept current?
- Are the settle / support / close weights (0.40 / 0.58 / 0.78) reasonable?
  How many tracks should "meeting the mood" last?
- Is "Let's bring the energy down gently" the right opening for a sad or lonely
  listener, who is already low-energy?
- A lyric review of the flagged Filipino tracks in `depressing` and `angry`.
- Should explicit tracks be filtered for all users or only on request?

---

## 11. Suggested slide outline and demo script

### Slides (~15–20 min)

1. **Title** — EmoTune: emotion-aware music, grounded in music therapy
2. **Problem** — music is used for mood regulation; recommenders ignore mood and outcome
3. **Solution in one picture** — the request flow (§2)
4. **The model** — 13 labels, BERT, two-stage training (§3.1–3.4)
5. **Data cleaning** — the dropped synthetic `sadness` class is a strong story (§3.3)
6. **Results** — 85% accuracy / 0.852 F1, per-label table, honest caveats (§3.5)
7. **Runtime fallback chain** (§4)
8. **Recommendation pipeline** — pool, search, personalization, ranker, taste control (§5)
9. **Therapy foundations** — iso-principle and the outcome routing (§6.1–6.2)
10. **The iso arc** — settle → support → close table (§6.3)
11. **Live demo** (below)
12. **Safety: protecting the person** — crisis layer + session design (§8.1–8.2)
13. **Safety: protecting what they hear** — content criteria, the `fear` list fix (§8.3)
14. **Safety: protecting their data** — the security table (§8.4)
15. **Testing** — 273 backend + 36 Flutter tests, QA results (§9)
16. **Limitations and next steps** (§10)
17. **Q&A**

### Demo script

1. Register (show the terms checkbox) → log in.
2. Type *"I have too many deadlines and no time"* → detected `stressed`, supportive
   text, first track plays at once, full playlist loads behind it.
3. Open the session studio → switch to *More discovery*, show the playlist change.
4. Type *"Grabe ang daming deadlines, stressed na ako"* → Taglish input
   (`stressed`, 0.97). Do **not** demo pure Tagalog — see §10.4.
   For `nostalgic`, use *"I miss my childhood days so much"* (0.99).
5. Use the Recommendations tab → pick `calm` directly.
6. Let a few tracks play → show the check-in prompt.
7. Type *"I want to end my life"* → crisis state: support message, no music.
   *(Use a phrase the list is known to catch; do not improvise this step live.)*
8. Show History and emotion stats → heart a track → show it in Favorites.

**Backup plan:** Spotify may rate-limit or reject non-allow-listed accounts
during a live demo. Record a screen capture of the full flow beforehand, and
demo from an allow-listed account.

---

## 12. Likely panel questions

**Why BERT and not an LLM API?** It runs locally at no per-request cost, needs
no network for classification, keeps user text private, and is fine-tuned for
our 13 labels and Taglish input. An LLM is optional and additive only (§5.4).

**Why 13 labels instead of the 6 basic emotions?** Music choice depends on
distinctions like lonely vs. sad or stressed vs. fear, which call for different
music. A reduced 8-label set is documented (`docs/EMOTION_LABELS.md`) in case
accuracy needs to trade off against granularity.

**How do you know the playlist helps?** Check-in answers and listen-through
behavior are stored per session; that is also the label the ranker trains on. A
formal user study is future work.

**What happens if the model is down or Spotify is down?** Every layer falls
back: GoEmotions or keywords for classification; the pool, curated lists or
fallback playlists for music. A broken component costs quality, never the
request.

**Isn't it dangerous for an app to respond to someone in crisis?** That is why
crisis text never reaches the music pipeline — the app steps aside and points to
human help. We also know the current detector is incomplete (§10.1) and treat
that as the top open item.

**Why was the manual mood-mode switch removed?** So a distressed user cannot opt
into a session that only amplifies the feeling; the classifier routes them to
de-escalation.

**Does it work in Filipino?** Partly. Taglish with English emotion words works
well; pure Tagalog is weak (5 of 7 misclassified in a spot check), because the
labelled training data is mostly English. The crisis phrases and the curated
music list do include Filipino. More Filipino training data is the top model
improvement (§10.4).

**What is the Plutchik profile for?** Explainability and visualization. It
never changes the prediction.
