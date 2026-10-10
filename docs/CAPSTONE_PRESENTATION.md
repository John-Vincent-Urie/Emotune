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

**EmoTune.** EmoTune uses a BERT-based emotion classifier to identify the
emotion expressed in a student's text (English or Taglish; Tagalog support is
still weak — §10.4). The backend maps the predicted emotion to a fixed collection
of songs validated by a music therapist and retrieves all active songs approved
for that emotion. The Flutter application displays the complete matching
collection and allows the student to choose a song. The system does not use a
machine-learning model to rank or personalize songs. During a session the app
checks in to ask whether the music is helping.

**What makes it more than a mood-to-genre lookup:**

- A domain-trained emotion model with an auditable fallback chain.
- A therapy-informed session arc that de-escalates distressing emotions instead
  of looping on them.
- A crisis-language safety net that stops the app from answering a crisis with a
  playlist.
- A song collection validated by a music therapist, shown in full: the student
  chooses, not an algorithm.

---

## 2. Architecture

| Part | Stack | Responsibility |
| --- | --- | --- |
| `flutter_app/` | Flutter (Dart), Provider | Mobile client: mood entry, playback, favorites, history, profile, session controls |
| `backend/` | Django 4.2 + Django REST Framework, SimpleJWT, MySQL | Emotion classification, crisis check, the therapist-approved song collection, Spotify auth/playback, persistence, admin |
| `ml_model/` | PyTorch, Hugging Face Transformers, scikit-learn | Offline training: BERT model, dataset cleaning, baselines |
| External | Spotify Web API + Spotify App Remote SDK | Playback of the approved songs on the device (never song selection) |

### End-to-end request flow

```
Student: "I feel overwhelmed with everything I need to finish."
   │
   ▼
Flutter ── POST /api/analyze/ { text, session_length } ──►
   │
Django:
   0. Validate the text (non-empty, at most 2,000 characters)
   1. Crisis-language check (safety.py) ── match? ──► support message, NO music
   2. Emotion classifier  → emotion + confidence + all 13 scores
   3. Map the label to its Emotion record (the label is the record's name)
   4. Query the database  → every active approved Song for that Emotion,
                            in the therapist's order (EmotionSong.position)
   5. Supportive response text; optional gentle check-in (concern tier)
   6. Save PromptHistory
   │
   ▼
Flutter shows ALL returned songs (+ total). The student picks one; matched songs
play in-app via Spotify, unmatched ones open a Spotify search. The app reports
listen time and shows check-in prompts.
```

The list arrives complete in one response: the lookup is a database query and
makes no Spotify call, so the song details still show if Spotify is down.

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

## 5. Music selection — the therapist-approved collection

### 5.1 The collection

`docs/music.md` is the music therapist's approved list: **13 emotions, 125
emotion–song approvals, 114 distinct songs** (some songs are approved for more
than one emotion). It is stored in three tables and seeded by data migration —
a frozen copy, so the database never silently drifts from what was approved:

```
Emotion (name = BERT label, display_name)
   1 ──< EmotionSong (position = therapist order) >── 1  Song (title, artist,
                                                        spotify_track_id, spotify_url,
                                                        album, image, is_active)
```

### 5.2 Selection is a query, not a model

For a detected emotion the backend returns every active song mapped to it, in
the therapist's order. Nothing scores, filters or reorders songs per user. The
mapping is tested directly: all of the emotion's active songs are returned,
none from another emotion, inactive songs are excluded, and a song approved
for several emotions appears once in each list.

### 5.3 Spotify's limited role

Each song's Spotify track ID was found **once, offline**, by exact title +
artist search and stored on the row (111 of 114 matched; original or official recordings only). Spotify is then used
only to play those stored tracks in-app. An unmatched song is still listed, with
a Spotify search link instead of a play button. Spotify never decides which
songs are suitable for an emotion.

### 5.4 What was removed (2026-10-10 refactor)

LightFM (collaborative filtering; it never ran on Python 3.12 and was already out
of the code), the linear ranker and its training, the optional LLM search
planner, Spotify search-based retrieval with its shared candidate pools,
personalization from Spotify history, progressive loading, and the taste
controls (More familiar / More discovery / Prefer instrumental).

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

### 6.2 Session modes — chosen by the classifier, not the user

| Mode | Check-in cadence | Emotions |
| --- | --- | --- |
| **Match my mood** | every 5 tracks | happy, surprising, motivational, calm, romantic, nostalgic, mixed |
| **Calm me down** | every 3 tracks | sad, stressed, depressing, angry, fear, lonely |

A mode shapes the listening session (check-in wording and cadence). It does not
change the songs: those are always the approved list for the detected emotion.

### 6.3 The iso-principle, in practice

The iso-principle — meet the mood first, then shift — is applied through the
check-in, not by blending songs. The session starts with the approved songs for
the emotion the student expressed. For a high-confidence sad, stressed,
depressing or angry reading, the app later asks "Are you feeling better right
now?"; answering yes switches the list to a support emotion's approved songs
(calm, or motivational for angry), again in the therapist's order.

### 6.4 Check-ins ("Are you feeling better?")

A session has a length (Auto / 15 / 20 / 45 min) and a check-in rhythm (§6.2).
At a checkpoint the app asks; the answer (`/api/feel-better-response/`) can
switch to the support emotion's list or close the session. The answer is stored
per session.

---

## 7. User-facing features

| Area | Features |
| --- | --- |
| **Onboarding / auth** | Welcome & splash screens, register (terms acceptance required), login, logout, **forgot password with a 6-digit email code**, change password, password strength meter |
| **Home** | Mood composer (free text, English/Taglish), detected emotion + confidence chip, supportive message, the complete approved song list for that emotion |
| **Session studio** | Session length and check-in frequency |
| **Recommendations tab** | Pick an emotion directly and see its approved songs |
| **Player** | Spotify App Remote playback, mini player + full player, queue, skip/seek/volume, playability tracking |
| **Favorites** | Heart a playable song; tagged with the emotion it was saved under |
| **History** | Past prompts, detected emotions, playlists, emotion statistics |
| **Profile** | Bio, avatar, preferred artists, Spotify connect/disconnect, theme |
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

Every list in `docs/music.md` was reviewed against five criteria and then
validated by the music therapist; only that validated list is ever shown. A
track is disqualified if it:

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
| **Consent** | Terms must be accepted at registration (timestamp stored); no personalization or training on listening data. |
| **Spotify** | OAuth with a signed state parameter; tokens refreshed server-side; disconnect endpoint; no Spotify listening history is read |
| **Transport / headers** | In production: HTTPS redirect, HSTS (1 year), secure + HttpOnly + SameSite cookies, `X-Frame-Options: DENY`, nosniff, strict referrer policy |
| **CORS** | Open only in debug; startup refuses the unsafe "all origins + credentials" combination in production |
| **Resilience** | Every layer degrades instead of failing: BERT → GoEmotions → keywords; songs come from the database, so Spotify outages never hide them |

---

## 9. Testing and QA

**Automated tests (backend, run 2026-10-10 after the refactor):** 186 tests, all
passing, with outbound network blocked; Django system and migration checks clean.
Flutter test results are to be refreshed after the app's matching update.

Backend coverage by area:

| Area | Tests |
| --- | --- |
| Core API: analysis, song lookup, Spotify auth/playback, admin (`api/tests.py`) | 70 |
| **Crisis safety** | **31** |
| Users / auth | 24 |
| Listening-session logging | 12 |
| Session length | 11 |
| **Password reset** | **11** |
| Session modes | 8 |
| Settings / security | 8 |
| Spotify rate limiting | 6 |
| Spotify failure classification | 5 |

**Manual live-API QA** confirmed: correct 401/403 handling, a user cannot reach
another user's session (404), and the password reset does not reveal accounts.

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
6. **Explicit flags are not checked.** Only therapist-validated songs are shown,
   but Spotify's `explicit` flag is not stored or filtered.
7. **3 of 114 songs have no Spotify match** (no original recording found), so they
   cannot play in-app; the app offers a Spotify search instead. Spotify
   Development Mode also limits playback to allow-listed accounts.
8. **The shift toward a support emotion happens only at check-ins,** not within a
   list; a student who never answers a check-in stays on the first list.
9. **Minor:** the feel-better endpoints return HTTP 500 on a non-numeric
   `history_id` (should be 400); Spotify tokens are stored unencrypted in the
   database.
10. **Not a clinical tool.** EmoTune is a wellbeing aid, not therapy or diagnosis.
    Therapeutic judgment calls (which songs validate sadness without
    romanticizing despair, when to escalate) need clinician review.

### Questions to bring to the music-therapist interview

- Which crisis phrasings (English and Filipino) should always trigger the safety
  response? Is a phrase list defensible at all, or should it always be paired
  with a model?
- Which Philippine crisis line should the app show, and how is it kept current?
- How many tracks should "meeting the mood" last before the first check-in?
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
8. **The song collection** — therapist list → database mapping, no ranking (§5)
9. **Therapy foundations** — iso-principle and the session modes (§6.1–6.2)
10. **Check-ins and the support switch** (§6.3–6.4)
11. **Live demo** (below)
12. **Safety: protecting the person** — crisis layer + session design (§8.1–8.2)
13. **Safety: protecting what they hear** — content criteria, the `fear` list fix (§8.3)
14. **Safety: protecting their data** — the security table (§8.4)
15. **Testing** — 186 backend tests, QA results (§9)
16. **Limitations and next steps** (§10)
17. **Q&A**

### Demo script

1. Register (show the terms checkbox) → log in.
2. Type *"I have too many deadlines and no time"* → detected `stressed`, supportive
   text, and all 10 approved stressed songs, in the therapist's order.
3. Pick a song from the list and play it; point out an unmatched song's Spotify
   search link.
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
our 13 labels and Taglish input.

**Why 13 labels instead of the 6 basic emotions?** Music choice depends on
distinctions like lonely vs. sad or stressed vs. fear, which call for different
music. A reduced 8-label set is documented (`docs/EMOTION_LABELS.md`) in case
accuracy needs to trade off against granularity.

**How do you know the playlist helps?** Check-in answers and listen-through
behavior are stored per session. A formal user study is future work; therapist
approval validates the song collection, not its clinical effectiveness.

**What happens if the model is down or Spotify is down?** Every layer falls
back: GoEmotions or keywords for classification. Songs come from the database,
so a Spotify outage only disables in-app playback — the list still shows.

**Isn't it dangerous for an app to respond to someone in crisis?** That is why
crisis text never reaches the music pipeline — the app steps aside and points to
human help. We also know the current detector is incomplete (§10.1) and treat
that as the top open item.

**Why was the manual mood-mode switch removed?** So a distressed user cannot opt
into a session that only amplifies the feeling; the classifier sets the session
mode, and the check-in can move them to a support emotion's approved songs.

**Does it work in Filipino?** Partly. Taglish with English emotion words works
well; pure Tagalog is weak (5 of 7 misclassified in a spot check), because the
labelled training data is mostly English. The crisis phrases and the curated
music list do include Filipino. More Filipino training data is the top model
improvement (§10.4).

**What is the Plutchik profile for?** Explainability and visualization. It
never changes the prediction.
