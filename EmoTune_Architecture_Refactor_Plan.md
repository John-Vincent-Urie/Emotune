# EmoTune Architecture Refactor Plan
## Remove LightFM and Use Therapist-Validated Static Song Mapping

**Purpose:** This document is the implementation brief for an AI coding assistant or developer working on the existing EmoTune repository.

## 1. Project Context

EmoTune is a mobile application intended to support students' emotional well-being by analyzing mood descriptions and displaying music associated with the detected emotion.

Current/retained stack:
- **Mobile frontend:** Flutter
- **Backend:** Django (and the project's existing REST API framework, if applicable)
- **Emotion classification:** Existing BERT-based classifier
- **Database:** Existing database, expected to be MySQL in the deployed setup
- **Music access:** Spotify links and/or supported Spotify metadata retrieval
- **Song collection:** Static collection of songs validated and approved by the project's music therapist

## 2. Main Decision

Remove **LightFM and all machine-learning-based song recommendation/ranking behavior**.

Keep:
- The existing BERT emotion classifier and tokenizer.
- Existing text preprocessing required by that classifier.
- Django API and database.
- Therapist-validated, static song collection.
- A deterministic emotion-to-song mapping.
- The Flutter music picker.
- Spotify integration only for supported music metadata or music access (for example, opening a stored Spotify link).

The picker must display **all active, therapist-approved songs mapped to the emotion predicted by BERT**. Do not rank, score, personalize, or filter songs using a recommendation model.

Therapist approved song
HAPPY
● Happy — Pharrell Williams
● Can't Stop the Feeling! — Justin Timberlake
● Best Day of My Life — American Authors
● Shake It Off — Taylor Swift
● Favorite Rings — Taylor Swift
● Salamin-Salamin — BINI
● Awitin Mo at Isasayaw Ko — VST & Company
● Walking on Sunshine — Katrina and the Waves
● Don't Stop Me Now — Queen
● Ligaya — Eraserheads

SAD
● Fix You — Coldplay
● Before It Sinks In — Moira Dela Torre
● Happier — Ed Sheeran
● The Night We Met — Lord Huron
● 12:51 — Krissy & Ericka
● Huling Sandali — December Avenue
● You'll Be in My Heart — NIKI
● Let Her Go — Passenger
● Blue — Yung Kai

ANGRY
● 21 Guns — Green Day
● Look What You Made Me Do — Taylor Swift
● Nosi Ba Lasi — Sampaguita
● Cool Off — Yeng Constantino
● ERE — Juan Karlos
● You Oughta Know — Alanis Morissette
● Cartier Gucci Scarf — Young Thug
● Narda — Kamikazee
● Halaga — Parokya ni Edgar
● Tatsulok — Bamboo

MOTIVATED
● Fireflies — Owl City
● I Will Survive — Demi Lovato
● Araw-Araw — Ben&Ben
● Kiss It Better — Rihanna
● Dance All Night — ROSÉ
● Graduation March - Holiday Celebration Troupe
● Fight Song — Rachel Platten
● Feels — Calvin Harris
● Hall of Fame — The Script ft. will.i.am
● Believer — Imagine Dragons

SCARED
● Kathang Isip — Ben&Ben
● Creep — Radiohead
● Somebody's Watching Me — Rockwell
● No Surprises — Radiohead
● Roar — Katy Perry
● With a Smile — Eraserheads
● I'm Scared — Young Thug
● Battle Belongs — Phil Wickham
● The Hills — The Weeknd
● Huwag Kang Matakot — Reese Lansangan

DEPRESSED
● Fix You — Coldplay
● Leaves — Ben&Ben
● Somebody Else — The 1975
● 505 — Arctic Monkeys
● Pahinga — Ben&Ben
● From the Start — Laufey
● Innocence — Hilder Svensson
● Valentine — Laufey
● With a Smile — Eraserheads
● 1-800-273-8255 — Logic ft. Alessia Cara & Khalid

NOSTALGIC
● Dati — Sam Concepcion
● Memories — Maroon 5
● Photograph — Ed Sheeran
● Every Woman in the World — Air Supply
● Ang Huling El Bimbo — Eraserheads
● 7 Years — Lukas Graham
● Perfect — Ed Sheeran
● Fireflies — Owl City
● Everybody Wants to Rule the World — Tears for Fears

ROMANTIC
● Perfect — Ed Sheeran
● Photograph — Ed Sheeran
● Misteryoso — Cup of Joe
● Bibingka — Ben&Ben
● Chest Pain — Malcolm Todd
● A Thousand Years — Christina Perri
● On Bended Knee — Boyz II Men
● Blue — Yung Kai
● Can't Help Falling in Love — Elvis Presley
● All of Me — John Legend
● Fill It — Young Thug
LONELY
● Iris — Goo Goo Dolls
● So Sick — Ne-Yo
● All by Myself — Celine Dion
● Always — Daniel Caesar
● Lonely — Justin Bieber & benny blanco
● Raining in Manila — Lola Amour
● Dancing on My Own — Robyn
● Sana — I Belong to the Zoo
● Kahit 'Di Mo Alam — South Border
● Weston Road Flows — Drake
● The A Team — Ed Sheeran

CALM
● Blue — Yung Kai
● Seasons — wave to earth
● Ocean Eyes — Billie Eilish
● Best Friend — Rex Orange County
● Weightless — Marconi Union
● Merry-Go-Round — Joe Hisaishi
● Leaves — Ben&Ben
● Bleeding Love — Leona Lewis
● River Flows in You — Yiruma
● Bawat Daan — Ebe Dancel

STRESSED
● Under Pressure — Queen & David Bowie
● We Belong Together — Mariah Carey
● Araw-Araw — Ben&Ben
● Leaves — Ben&Ben
● Night Dancer — imase
● Pressure — Paramore
● Stressed Out — Twenty One Pilots
● Hallelujah — Boyce Avenue
● No One Noticed — The Marías
● This Side of Paradise — Coyote Theory

SURPRISED
● Bang Bang — Jessie J, Ariana Grande & Nicki Minaj
● Misteryoso — Cup of Joe
● Wake Me Up — Avicii
● Versace on the Floor — Bruno Mars
● All I Do Is Win — DJ Khaled
● Surprise Yourself — Jack Garratt
● Dynamite — BTS
● I'm Nilalangam — Cesca
● Ilaw sa Daan — IV of Spades
● Swiss Beats — Young Thug

MIXED
● Happier — Marshmello & Bastill
● The Day You Said Goodnight — Hale
● Kahit Ayaw Mo Na — This Band
● Pasilyo — SunKissed Lola
● Castle on the Hill — Ed Sheeran
● Whatever It Takes — Imagine Dragons

The song collection is maintained by developers through controlled database changes, fixtures, or migrations. Do not build an admin song-management interface unless one already exists and is required for another reason.

## 3. Target Architecture

```text
Student
  |
  v
Flutter mobile application
  |  HTTPS / REST API
  v
Django API
  |
  +--> Validate request text
  |
  +--> Existing BERT classifier
  |       |
  |       v
  |    Predicted emotion label
  |
  +--> Map classifier label to a supported database emotion
  |
  +--> Query database for all active songs mapped to that emotion
  |
  v
Return emotion + complete matching song list
  |
  v
Flutter displays all returned songs
  |
  +--> Optional: open stored Spotify URL / use supported Spotify metadata
```

Spotify must not decide which songs are suitable for an emotion. The approved database mapping is the source of truth. If Spotify is unavailable, the app should still display stored song details.

## 4. Expected Workflow

1. Student enters a description of their current mood in Flutter.
2. Flutter submits the text to Django over HTTPS.
3. Django validates the request (including non-empty text and a reasonable maximum length).
4. Django calls the existing BERT inference implementation, using its existing tokenizer and preprocessing.
5. The classifier returns a predicted emotion label. If the model exposes confidence scores, these may be retained for internal diagnostics or a separately designed uncertainty policy; do not invent scores if the model does not provide them.
6. Django maps the classifier output to a supported emotion record. Use an explicit label mapping if the model returns values such as `LABEL_3` rather than database emotion names.
7. Django retrieves every active song associated with the matched emotion.
8. Django returns the emotion and complete song list to Flutter.
9. Flutter displays all songs, with title, artist, and an available Spotify link or supported metadata.
10. The student manually chooses a song. This is user choice, not AI ranking.

If the label is unsupported, do not return an unrelated playlist. Return a clear, safe response. If no active songs are mapped to a valid emotion, return an empty list with a suitable message.

## 5. Database Design

Adapt these suggestions to the existing models rather than replacing working models without inspection.

### `Emotion`
Suggested fields:
- `id`: primary key
- `name`: unique canonical emotion label
- `description`: optional

Emotion names must be consistent with the BERT label mapping. EmoTune has used these 13 categories in project planning:
- happy
- sad
- angry
- stressed
- calm
- lonely
- romantic
- nostalgic
- motivational
- fear
- depressing
- surprising
- mixed emotions

**Important:** Verify the exact labels produced by the trained model and the existing database before changing names. Preserve any established mapping or normalization rules.

### `Song`
Suggested fields:
- `id`: primary key
- `title`
- `artist`
- `spotify_track_id`: nullable if not available
- `spotify_url`: nullable if not available
- `is_active`: boolean indicating whether the song may be shown

Retain other existing fields if they serve the UI or another feature, such as album artwork or cached metadata. Do not add BPM, valence, or other fields solely for removed ranking behavior.

### `EmotionSong` mapping
Suggested fields:
- `id`: primary key
- `emotion_id`: foreign key to `Emotion`
- `song_id`: foreign key to `Song`

Enforce uniqueness on `(emotion_id, song_id)` to prevent duplicate mappings. A song may be mapped to multiple emotions only where the therapist has approved those mappings.

In Django, this may instead be implemented as a `ManyToManyField` from `Song` to `Emotion` with an explicit `through` model. Follow the repository's current conventions.

### Static collection maintenance
- Developers maintain the song data using controlled fixtures, migrations, or documented database changes.
- Do not create a new admin interface just for this refactor.
- Store verified Spotify IDs/URLs where possible; do not rely on live Spotify search to rediscover a track by title every time.
- Use migrations for schema changes and preserve existing data.
- Never invent therapist approvals. Use the actual validated song list supplied by the project.

## 6. API Design

Inspect existing API routes first and reuse/update them when practical. Do not create duplicate endpoints unnecessarily.

Suggested primary endpoint:

`POST /api/emotions/analyze/`

Request:
```json
{
  "text": "I feel overwhelmed by all my school requirements."
}
```

Illustrative response (song details are placeholders):
```json
{
  "emotion": {
    "id": 4,
    "name": "stressed"
  },
  "songs": [
    {
      "id": 12,
      "title": "Example Song A",
      "artist": "Example Artist A",
      "spotify_url": "https://open.spotify.com/track/EXAMPLE_ID"
    },
    {
      "id": 18,
      "title": "Example Song B",
      "artist": "Example Artist B",
      "spotify_url": "https://open.spotify.com/track/EXAMPLE_ID_2"
    }
  ],
  "total": 2
}
```

The actual response must be populated from the database. Do not include placeholder songs in production.

Optional endpoints, only if useful to the current app:
- `GET /api/emotions/` — list supported emotions
- `GET /api/emotions/{emotion_id}/songs/` — list all active songs mapped to a specific known emotion

Do not expose an endpoint that allows the client to claim an emotion prediction without server-side validation unless there is a separate, justified use case.

## 7. Backend Query Requirements

The backend lookup must:
- Select all active songs mapped to the predicted emotion.
- Avoid LightFM scores, recommendation probabilities, personalized ranking, and learned filters.
- Use deterministic display ordering if needed, such as title then ID.
- Avoid duplicate song records.
- Return a valid empty list if no songs are mapped.
- Serialize only fields needed by Flutter.
- Keep BERT inference on the backend; do not move model weights or inference logic into Flutter.

Illustrative service pseudocode (adapt to actual model relationships):

```python
def analyze_mood_and_get_songs(text):
    if not text or not text.strip():
        raise ValidationError("Text is required.")

    predicted_label = bert_predict(text)  # Existing project inference function
    emotion_name = map_model_label(predicted_label)

    emotion = Emotion.objects.filter(name=emotion_name).first()
    if emotion is None:
        return {
            "emotion": None,
            "songs": [],
            "message": "No supported emotion was identified."
        }

    songs = (
        Song.objects.filter(emotions=emotion, is_active=True)
        .order_by("title", "id")
        .distinct()
    )

    serialized_songs = serialize_songs(songs)  # Implement with current serializer
    return {
        "emotion": {"id": emotion.id, "name": emotion.name},
        "songs": serialized_songs,
        "total": len(serialized_songs)
    }
```

This is pseudocode, not guaranteed drop-in code. `bert_predict`, `map_model_label`, `emotions`, and `serialize_songs` must be adapted to the actual repository. Follow existing error-handling and serializer conventions.

## 8. Flutter Changes

Update the current mood-analysis and music-picker flow so that Flutter:
- Sends the student's text to the existing/new primary API endpoint.
- Parses the returned emotion and song list.
- Displays every returned song, not just one top-ranked result.
- Displays song title and artist, and a Spotify link or supported music action when available.
- Handles loading, validation errors, network errors, server errors, unsupported labels, and empty song lists.
- Does not calculate recommendation scores or reorder songs by a model.
- Does not require Spotify to be reachable just to render stored song details.

Use the project's current state-management and networking conventions. Avoid introducing new packages unless needed.

## 9. Spotify Behavior

Spotify is optional for accessing music details or opening music links, not for selecting songs.

- The database mapping is the source of truth for eligibility.
- Prefer stored, verified Spotify track IDs or URLs.
- Do not run a Spotify search for every mood submission as a replacement for the approved collection.
- If Spotify metadata lookup fails, still return and show the stored title/artist.
- If a link is absent, show the song without a Spotify action or provide a clear unavailable state.
- Opening an external Spotify URL is not the same as in-app audio playback. Do not promise direct playback unless the existing implementation and current Spotify permissions/account requirements support it.

## 10. Remove LightFM Carefully

Before deleting files or packages, search the repository for all references to:
- `LightFM`
- LightFM model loading and prediction
- recommendation training scripts and serialized model artifacts
- user-item interaction matrices used only by LightFM
- recommendation scores, ranking services, and model-specific API fields
- Flutter UI elements that display recommendation ranks/scores

Then:
1. Identify all code paths and imports.
2. Replace the song selection path with deterministic database lookup.
3. Update or remove obsolete API fields and UI dependencies.
4. Run tests and the app.
5. Remove LightFM-only packages and artifacts from dependencies only after verifying they are not used elsewhere.
6. Keep shared BERT dependencies.
7. Do not delete listening history, favorites, BPM, valence, or other data automatically; first verify whether another feature still uses them.

## 11. Testing and Acceptance Criteria

The refactor is complete when all applicable criteria pass:

### Emotion inference
- Existing BERT model still loads and performs inference.
- Existing preprocessing and tokenizer behavior are preserved.
- Model labels map correctly to canonical database emotion labels.

### Song lookup
- Every active song mapped to the predicted emotion is returned.
- No song mapped only to another emotion is returned.
- Inactive songs are excluded.
- Duplicate mappings do not cause duplicate response records.
- Results use deterministic ordering if ordering is specified.
- Empty mappings return an empty list and a clear response.
- Unsupported labels do not return an unrelated playlist.

### API and Flutter
- Empty or whitespace-only input is rejected.
- Malformed requests receive a suitable client error.
- Flutter displays all returned songs.
- Loading, network failure, server failure, and empty states are handled.
- Song details remain visible when Spotify is unavailable.
- Students can open available Spotify links using the supported behavior.

### Regression and cleanup
- No active code path depends on LightFM for music selection.
- No stale API field or UI component requires recommendation scores.
- Shared BERT dependencies remain installed.
- Database migrations preserve existing song and emotion data.
- Existing unrelated functionality still works.

### Capstone evaluation
Evaluate BERT classification performance separately from deterministic mapping correctness. Therapist approval of the song collection validates the mapping process; it does not by itself establish clinical effectiveness or guarantee a particular emotional outcome.

## 12. Documentation Updates

Update these project artifacts to match the implementation:
- System architecture diagram
- Data Flow Diagram (DFD)
- Entity Relationship Diagram (ERD)
- Methodology and system workflow
- Algorithm/pseudocode description
- API documentation
- Test plan and results
- Any references to LightFM-based personalized ranking

Suggested system description:

> EmoTune uses a BERT-based emotion classifier to identify the emotion expressed in a student's text. The backend maps the predicted emotion to a fixed collection of songs validated by a music therapist and retrieves all active songs approved for that emotion. The Flutter application displays the complete matching collection and allows the student to choose a song. The system does not use a machine-learning model to rank or personalize songs.

Do not claim that EmoTune diagnoses or treats mental-health conditions. Describe it as a system designed to support emotional well-being through therapist-validated music selection.

## 13. Instructions to the Coding AI

Work against the **existing repository**. Do not assume the names of current files, models, routes, serializers, or inference functions.

Before editing:
1. Inspect the repository structure and relevant Django and Flutter code.
2. Identify how BERT is loaded and how its current emotion labels are represented.
3. Identify the current LightFM integration and all dependencies on it.
4. Inspect the current song database schema and Spotify implementation.
5. Provide a short summary of the planned file-level changes.

Then implement the smallest safe refactor that satisfies this document. Preserve working behavior unrelated to LightFM. Use migrations for database schema changes, add or update tests, run the relevant test suite where possible, and report:
- Files changed
- Schema/API changes
- LightFM components removed
- Tests run and results
- Any unresolved assumptions or manual steps

Do not fabricate test results, Spotify capabilities, therapist approvals, or song data. If required repository details or the approved song list are missing, identify the gap rather than guessing.
