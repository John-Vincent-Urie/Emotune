# How BERT Processes Text for Music Selection in EmoTune

This is the actual flow used in this project.

Important idea: **BERT does not directly choose a song.**  
BERT's job is to turn the user's text into an **emotion prediction**. That prediction is then passed into the recommendation layer, which searches, filters, and ranks music.

## 1. Big Picture

```text
User text
  -> BERT tokenizer
  -> BERT emotion classifier
  -> emotion score distribution
  -> outcome-mode adjustment
  -> Spotify query building
  -> candidate track ranking
  -> selected track / playlist
```

## 2. The BERT-to-Music Matrix

| Stage | What happens to the text | Output | How the output is used for music |
| --- | --- | --- | --- |
| 1. Request input | The API receives `text` in `analyze_emotion`. | Raw user sentence | Starts the whole pipeline |
| 2. Tokenization | The tokenizer converts the sentence into BERT input tensors. In code it uses `truncation=True`, `padding=True`, and `max_length=128`. | Token IDs and attention-ready tensors | Makes the sentence readable by the BERT model |
| 3. BERT forward pass | The fine-tuned model runs a classification pass over the tokens. | 13 raw class logits | These are the model's unnormalized scores |
| 4. Softmax | Logits are converted into probabilities with `softmax`. | Emotion probabilities for all labels | This becomes the emotion score map |
| 5. Ranking | The system sorts the probabilities from highest to lowest. | Top emotion, second emotion, confidence margin | Used to decide whether the result is strong enough |
| 6. Confidence check | The model checks thresholds: high confidence at `>= 0.68`, medium at `>= 0.45`, and also checks margin `>= 0.12`. | `high`, `medium`, or low-confidence result | Decides whether to trust BERT or use fallback logic |
| 7. Result packaging | The classifier builds a result object with the top label and all score details. | `emotion`, `all_scores`, `top_emotions`, `secondary_emotion`, `confidence_band` | This is the handoff from NLP to recommendation |
| 8. Outcome-mode adjustment | The base emotion profile can be shifted by modes like `match_mood`, `calm_me_down`, `lift_me_up`, `help_me_focus`, or `sleep`. | `recommendation_target_emotion` | Lets the app recommend for the user's desired direction, not only current mood |
| 9. Spotify query building | The recommendation service uses the target emotion, top emotions, and score map to build layered search queries. | Search phrases such as emotion phrases, genre phrases, fallback phrases, and artist-biased phrases | Produces track candidates from Spotify |
| 10. Candidate ranking | Tracks are merged, sanitized, and scored for emotional fit, personalization, source quality, keywords, genres, and preferred artists. | Ranked track list | Picks the best track first and orders the playlist |
| 11. Final selection | Initial requests return a quick primary track; full requests can be re-ranked by LightFM. | `selected_track` and `tracks` | Final music returned to the user |

## 3. What BERT Is Actually Predicting

The saved model is a fine-tuned **`bert-base-uncased`** classifier with these 13 labels:

- `happy`
- `sad`
- `angry`
- `motivational`
- `fear`
- `depressing`
- `surprising`
- `stressed`
- `calm`
- `lonely`
- `romantic`
- `nostalgic`
- `mixed`

So when a user writes something like:

```text
I feel overwhelmed and tired because of deadlines.
```

the system does not search Spotify with that full sentence first.

It first turns that sentence into something more like:

```json
{
  "stressed": 0.61,
  "sad": 0.14,
  "fear": 0.10,
  "calm": 0.04,
  "mixed": 0.03
}
```

That score map is the important bridge between text understanding and music selection.

## 4. Step-by-Step Explanation

### Step 1: User text enters the API

`backend/api/views.py` reads the text inside `analyze_emotion`.

If the text is empty, the API returns an error.  
If text exists, it calls:

```python
classifier.predict(text)
```

i am bored

calm 3
happy 1
sad 0


### Step 2: BERT tokenizes the sentence

Inside `backend/ml/emotion_classifier.py`, the tokenizer prepares the sentence for the model:

```python
inputs = self.tokenizer(
    text,
    return_tensors='pt',
    truncation=True,
    max_length=128,
    padding=True,
)
```

This means:

- the text is converted into token IDs
- very long text is cut to 128 tokens
- shorter text is padded
- the output becomes PyTorch tensors

Because the saved model is based on `bert-base-uncased`, the tokenizer follows BERT's uncased tokenization behavior.

### Step 3: BERT predicts emotion logits

The model runs this:

```python
outputs = self.model(**inputs)
```

The output contains **logits**, which are raw scores for each emotion label.  
They are not yet probabilities.

### Step 4: Logits become probabilities

The code applies:

```python
probs = torch.softmax(outputs.logits, dim=1)
```

Now every label gets a probability between `0` and `1`, and the probabilities sum to `1`.

Then the code maps those values into the project's emotion names:

```python
bert_scores = {
    self.model_label_map[index]: float(probs[index])
    for index in range(...)
}
```

This creates the full emotion distribution.

### Step 5: The system decides how much it trusts BERT

The classifier sorts the scores and checks:

- top confidence
- confidence margin between first and second label

Default thresholds in this project:

- high confidence: top score `>= 0.68` and margin `>= 0.12`
- medium confidence: top score `>= 0.45`
- otherwise: low confidence

This matters because the app should not overreact to a weak prediction.

### Step 6: Fallback logic can replace weak BERT output

If BERT is weak or unavailable:

1. it tries the GoEmotions fallback model
2. if that is still not usable, it uses keyword matching
3. if nothing is strong enough, it returns a more uncertain `mixed`-leaning distribution

So the pipeline is **BERT first**, not BERT only.

### Step 7: The classifier returns a structured emotion profile

The result object includes more than one label. It includes:

- `emotion`: the top label
- `confidence`: the top score
- `all_scores`: full probability map
- `top_emotions`: top ranked emotions
- `secondary_emotion`
- `confidence_band`
- `confidence_margin`
- `plutchik_scores`

This is important because the music selector uses the whole emotional profile, not just one word.

## 5. How the Emotion Result Becomes Music

### A. Outcome mode may shift the target

Before searching for songs, the app may adjust the raw emotion result.

Example:

- detected by BERT: `stressed`
- user outcome mode: `calm_me_down`
- recommendation target may shift toward `calm`

So there are two separate ideas:

- **detected emotion** = what the user seems to feel
- **target emotion** = what kind of music the app should aim for

### B. Spotify queries are built from emotion signals

The recommendation service uses:

- primary emotion
- top emotions
- score map
- preferred artists
- playlist category

to build multiple Spotify search queries, from strongest match to broader fallback queries.

That means BERT's output influences:

- which emotion phrase is searched
- which related moods are included
- which genres and keywords are boosted
- which fallback phrases are used if the first searches are weak

### C. Candidate tracks are ranked

After candidate tracks are fetched, the system scores them using things like:

- emotional keyword fit
- genre fit
- preferred artists
- personalization score
- recommendation source
- taste profile

For the first response, the app quickly returns a primary track.  
For fuller playlist generation, the app can also use the local **LightFM** ranker to reorder candidates based on listening history and interaction data.

## 6. The Most Important Concept

If you want the simplest explanation:

**BERT converts free text into an emotion probability distribution, and that distribution controls the music search and ranking strategy.**

So the path is:

```text
"I feel stressed and overwhelmed"
-> BERT says "mostly stressed, a bit sad/fear"
-> system may change target to "calm" if outcome mode asks for that
-> Spotify queries are built around that emotional target
-> tracks are ranked by how well they match that target
-> best track / playlist is returned
```

## 7. Main Files Involved

- `backend/api/views.py`
- `backend/ml/emotion_classifier.py`
- `backend/ml/plutchik_mapper.py`
- `backend/api/recommendation_session.py`
- `backend/api/spotify_service.py`
- `backend/api/lightfm_ranker.py`
