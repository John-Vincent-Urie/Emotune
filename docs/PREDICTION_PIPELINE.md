# EmoTune — Prediction Pipeline

How one sentence of free text becomes one of 13 emotion labels, and then a
single track that plays. [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) §3 summarizes
the classifier as a layered component; this document is the detailed version —
the exact decision path, the thresholds it turns on, where the weights came
from, and what the architecture does *not* claim.

Two models do the work, and a regex that runs before either of them can refuse
the whole request.

---

## 1. The path a sentence takes

Six stages between the text box and the speaker. Only stage 2 is a neural
network; the stages around it are what make its output safe to act on.

| # | Stage | Lives in |
| --- | --- | --- |
| 00 | **Crisis gate** — regex over the raw text; a match stops the request here | `backend/api/safety.py` |
| 01 | **Tokenize** — WordPiece, truncated to 128 tokens | `backend/ml/emotion_classifier.py` |
| 02 | **BERT forward pass + softmax** — 13 probabilities summing to 1 | `backend/ml/emotion_classifier.py` |
| 03 | **Confidence cascade** — thresholds and margin decide whether BERT's answer stands | `backend/ml/emotion_classifier.py` |
| 04 | **Outcome routing** — mirror the mood, or steer it toward calm | `backend/api/recommendation_session.py` |
| 05 | **Candidate retrieval** — keywords/genres → Spotify search, plus curated seeds | `backend/api/spotify/` |
| 06 | **Ranking** — one dot product per candidate over 8 features | `backend/api/picker_ranker.py` |

---

## 2. The gate before the model

`assess_crisis_risk(text)` matches the raw input against a phrase list *before*
any inference runs. It is called at both free-text entry points —
`analyze_emotion` and `recommend_by_emotion` (`backend/api/views.py`).

On a hit, `_build_crisis_response_payload()` builds the response by hand:

- `tracks: []` — this path must never hand back a playlist
- `emotion: 'mixed'`, `confidence: 0.0`, all scores zeroed
- `prediction_strategy: 'crisis_short_circuit'`
- `ai_response` carries the support message instead of music

The payload is shaped like a normal `EmotionResponseBuilder.build()` result, so
a client that doesn't yet branch on `crisis` still gets a coherent "no tracks,
here's a message" response rather than a differently-shaped one it has to guess
about.

**Why it is not a model.** A classifier that is ~85% accurate is an odd thing to
put in front of a life-safety decision. A phrase list fails in a direction you
can reason about and audit. The trade is recall — it catches what it lists and
nothing else.

> Any new endpoint that accepts free text has to call `assess_crisis_risk`
> itself, or it bypasses the gate entirely. This is the easiest way to
> accidentally regress the most important behavior in the system.

---

## 3. The confidence cascade

BERT does not get the last word — it gets the *first* word, and keeps it only if
it is both confident enough and decisive enough.

The 13 softmax scores are ranked descending, and
`margin = top score − second score`. Margin matters separately from confidence:
a high score with a thin margin means the model is torn between two labels,
which is a different failure from simply being unsure.

```
13 softmax probabilities
  │
  ├─ confidence ≥ 0.68 AND margin ≥ 0.12 ──→ bert_high_confidence
  │                                          accepted; needs_review: false
  │
  ├─ confidence ≥ 0.45 ────────────────────→ bert_medium_confidence
  │                                          used, but uncertain: true
  │
  ├─ GoEmotions second opinion ────────────→ goemotions_low_confidence_fallback
  │    SamLowe/roberta-base-go_emotions        accepted only if it clears
  │    28 labels → 13 via GOEMOTIONS_LABEL_MAP  its own 0.30 / 0.05 thresholds
  │
  └─ keyword scorer ───────────────────────→ keyword_fallback
       KeywordEmotionScorer + HEARTBREAK_PATTERNS   always returns something
```

Thresholds are configurable (`EMOTION_HIGH_CONFIDENCE_THRESHOLD`,
`EMOTION_MEDIUM_CONFIDENCE_THRESHOLD`, `EMOTION_MIN_MARGIN_THRESHOLD`); the
defaults above are `DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.68`,
`DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD = 0.45`,
`DEFAULT_MIN_MARGIN_THRESHOLD = 0.12`.

The same ladder runs in three situations — normal low confidence, BERT weights
failing to load (`model_not_loaded`), and the forward pass throwing
(`bert_prediction_error`). The entry points differ; the ladder is identical.
There is no code path where a request returns nothing because a model was
missing.

**Every prediction carries its own provenance.** Alongside `emotion`,
`confidence` and the full `all_scores` vector, `_build_result()` returns
`prediction_source`, `prediction_strategy`, `confidence_band`,
`confidence_margin`, `fallback_used`, `fallback_reason`, `needs_review`, the top
2 emotions, a `secondary_emotion`, and a Plutchik profile. Given any response,
you can say which of the four paths produced it.

---

## 4. Thirteen labels, two routes

The predicted label does two jobs: it names the feeling, and it decides whether
the session mirrors that feeling or moves away from it
(`EMOTION_OUTCOME_MODES`, `backend/api/recommendation_session.py`).

| Route | Labels |
| --- | --- |
| `match_mood` — mirrored | happy, motivational, surprising, calm, romantic, nostalgic, mixed |
| `calm_me_down` — steered | sad, angry, fear, depressing, stressed, lonely |

`mixed` is mirrored on purpose: it means the classifier could not commit, and
steering someone toward calm when there is no evidence of distress presumes more
than the signal supports.

For a steered label the predicted emotion is blended against a calmer target,
and the blend weight moves with the session phase — the iso-principle arc:

| Phase | `target_weight` | Intent |
| --- | --- | --- |
| `settle` | 0.40 | meet the listener where they are |
| `support` | 0.58 | transition |
| `close` | 0.78 | arrive at the steadier state |

A label with no seat in `target_weights` is discounted a second time by
`base_weight`, capping it at `base_weight**2`, so it can never outrank a real
target emotion at the close of a session. See
[music_therapy_guidelines.md](music_therapy_guidelines.md) for the clinical
rationale behind both the routing table and the arc.

---

## 5. Where the weights came from

Staged fine-tuning from `bert-base-uncased` (`ml_model/train_bert.py`). A large
public corpus teaches general emotion structure; a small hand-built EmoTune set
teaches the 13-label schema. The final stage warm-starts from the stage-1
checkpoint rather than from scratch.

- **Architecture** — `BertForSequenceClassification`, 12 layers, 768 hidden,
  12 attention heads, `single_label_classification`, 13 labels
- **Final stage** — `emotune_combined.csv`, custom repeat factor 3
- **Artifact** — `backend/ml/models/bert_emotion_model/`

| Metric | Value |
| --- | --- |
| Validation accuracy | 0.848 |
| Macro F1 | 0.839 |
| Weighted F1 | 0.851 |
| Train examples | 3,369 |
| Validation examples | 99 |
| Epochs | 4 |

Final-stage class balance:

| Label | Train | Val | Class weight |
| --- | --- | --- | --- |
| happy, sad | 285 | 8–9 | 0.91 |
| romantic | 279 | 8 | 0.93 |
| angry, motivational, depressing, surprising, stressed, calm, lonely, nostalgic | 276 | 8–9 | 0.94 |
| fear | 273 | 8 | 0.95 |
| **mixed** | **39** | **1** | **6.64** |

Twelve labels sit within 4% of each other. `mixed` does not — see §7.

---

## 6. The second model

The classifier picks the emotion; it does not pick the song. That is a separate,
much simpler model (`backend/api/picker_ranker.py`): a weighted sum over eight
precomputed signals, one dot product per candidate. No model fitting at request
time, no native extension, no extra process memory.

The weights are data, not code — `ml_model/train_picker_ranker.py` fits them
offline from real listening outcomes and writes a JSON artifact. Until that
artifact exists, these defaults reproduce the hand-tuned blend that shipped
before:

| Feature | Weight |
| --- | --- |
| `emotion_alignment` | 0.80 |
| `personalization` | 0.10 |
| `availability` | 0.07 |
| `popularity` | 0.03 |
| `discovery_fit` | 1.00 |
| `instrumental_fit` | 1.00 |
| `is_preferred` | 0.00 |
| `familiar_source` | 0.00 |

The two taste terms pass through at 1.00 because they arrive pre-scaled — they
are not eighty times more important than popularity. `emotion_alignment` at 0.80
is the real statement: what the classifier decided dominates every other signal
by an order of magnitude.

---

## 7. What this architecture does not claim

Worth stating plainly in the write-up before a reviewer states it for you.

1. **85% accuracy is measured on 99 rows.** The confidence interval on that
   number is wide. Report it as a validation figure, not as expected real-world
   performance.

2. **`mixed` is effectively unmeasured.** 39 training rows carrying a 6.6×
   class weight, against a single validation example. Whatever the macro F1 says
   about that class is computed from one row.

3. **The medium band does not check the margin.** The high band requires
   confidence ≥ 0.68 *and* margin ≥ 0.12. The medium band checks confidence
   only, so a prediction split near-evenly between two labels (0.50 / 0.49) is
   served as a medium-confidence answer. It is flagged `uncertain`, but the label
   still routes the session.

4. **Truncation at 128 tokens is silent.** A long message is cut before the
   model reads it, with nothing in the response saying so. Someone who writes
   several paragraphs may be classified on the first half of what they said.

5. **The crisis gate is recall-limited by construction.** A phrase list catches
   phrasings it lists. Indirect expressions of risk pass through to the
   classifier and receive a playlist. This is a known boundary of the current
   design, not an oversight — but it is the boundary that matters most.

---

## Related documents

- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) — what the whole system is and how the parts fit
- [music_therapy_guidelines.md](music_therapy_guidelines.md) — the clinical rationale behind the routing and the content rules
- [EMOTION_LABELS.md](EMOTION_LABELS.md) — the label set
- [MODEL_TRAINING_RESULTS.md](MODEL_TRAINING_RESULTS.md) — full training run results
