# EmoTune Database Design Guide

## Purpose

This file explains how to create the **Entity Relationship Diagram (ERD)** and the **data normalization documentation** for the EmoTune system based on the current project database.

The sample pictures you shared are only examples of style. The actual ERD and normalization for EmoTune should follow the real stored data in this system.

## Scope of the Current EmoTune Database

The current app uses Django with SQLite in development, and the project-specific stored entities are mainly found in the `users` app.

The real core entities currently stored by EmoTune are:

1. **User**
2. **PromptHistory**
3. **ListeningSession**
4. **FavoriteTrack**
5. **UserPreference**

Important note:

- **Administrator is not a separate database table** in the current project.
  Admin access is handled through the same user model using Django auth roles and permissions.
- **Spotify API is not an entity in the ERD** because it is an external service, not a local database table.

## Difference Between ERD and Normalization

- The **ERD** shows the entities, their attributes, primary keys, foreign keys, and relationships.
- **Normalization** explains how the table structure avoids redundancy and dependency problems.

Use the ERD to show:

- what tables exist
- how they connect
- what each table stores

Use normalization to explain:

- whether each table has atomic columns
- whether non-key attributes depend on the whole key
- whether transitive dependencies were removed

## Recommended ERD Symbols

Use standard ERD notation such as Crow's Foot or Chen notation.

At minimum, show:

- **Entity box**
- **Primary key**
- **Foreign key**
- **Relationship line**
- **Cardinality** such as `1-to-many`

## Main Entities for EmoTune

## 1. User

This is the main account table for all normal users and admins.

Recommended attributes to show:

- `id` or `user_id` as **Primary Key**
- `username`
- `email`
- `password`
- `terms_accepted_at`
- `personalization_opt_in`
- `spotify_id`
- `spotify_access_token`
- `spotify_refresh_token`
- `spotify_granted_scopes`
- `spotify_token_expires`
- `profile_picture`
- `bio`
- `is_spotify_connected`
- `preferred_artists`
- `created_at`
- `updated_at`

Important note for ERD writing:

- You may show `is_staff` and `is_superuser` only if you want to explain admin access.
- Do not create a separate **Administrator** entity unless your design is conceptual rather than strictly based on the current schema.

## 2. PromptHistory

This stores the user's submitted text prompt, the detected emotion, the response text, and the recommendation context.

Recommended attributes to show:

- `id` as **Primary Key**
- `user_id` as **Foreign Key**
- `prompt_text`
- `detected_emotion`
- `emotion_confidence`
- `emotion_scores`
- `ai_response`
- `playlist_data`
- `music_picker_data`
- `session_duration`
- `felt_better_response`
- `created_at`

## 3. ListeningSession

This stores playback-related listening records tied to a prompt history item.

Recommended attributes to show:

- `id` as **Primary Key**
- `user_id` as **Foreign Key**
- `prompt_history_id` as **Foreign Key**
- `spotify_track_id`
- `track_name`
- `listen_duration`
- `completed`
- `created_at`

## 4. FavoriteTrack

This stores tracks that a user has saved as favorites.

Recommended attributes to show:

- `id` as **Primary Key**
- `user_id` as **Foreign Key**
- `spotify_track_id`
- `track_name`
- `artist_name`
- `album_name`
- `album_image`
- `preview_url`
- `duration_ms`
- `added_at`

Important constraint:

- `user_id + spotify_track_id` is unique for each favorite record.

## 5. UserPreference

This stores learned preference signals for a user, per emotion, per track.

Recommended attributes to show:

- `id` as **Primary Key**
- `user_id` as **Foreign Key**
- `emotion`
- `spotify_track_id`
- `track_name`
- `artist_name`
- `play_count`
- `last_played`
- `total_listen_time`

Important constraint:

- `user_id + emotion + spotify_track_id` is unique.

## Relationships in the EmoTune ERD

Use these relationships in the diagram:

1. **User 1-to-many PromptHistory**
   One user can create many prompt history records.

2. **User 1-to-many ListeningSession**
   One user can have many listening sessions.

3. **User 1-to-many FavoriteTrack**
   One user can save many favorite tracks.

4. **User 1-to-many UserPreference**
   One user can have many learned preference records.

5. **PromptHistory 1-to-many ListeningSession**
   One prompt history record can be linked to many listening session records.

## Recommended ERD Layout

A clean layout for the EmoTune ERD is:

- place **User** in the center
- place **PromptHistory** on one side
- place **ListeningSession** below `PromptHistory`
- place **FavoriteTrack** on another side of `User`
- place **UserPreference** on the remaining side

This works well because `User` is the parent entity for most records.

## Instructions for Drawing the ERD

Follow these steps:

1. Draw an entity box for **User**.
2. Mark `id` as the primary key.
3. Add the important descriptive attributes.
4. Draw an entity box for **PromptHistory**.
5. Mark `id` as the primary key and `user_id` as a foreign key.
6. Connect **User** to **PromptHistory** with a `1-to-many` relationship.
7. Draw an entity box for **ListeningSession**.
8. Mark `id` as the primary key and add `user_id` and `prompt_history_id` as foreign keys.
9. Connect **User** to **ListeningSession** with `1-to-many`.
10. Connect **PromptHistory** to **ListeningSession** with `1-to-many`.
11. Draw an entity box for **FavoriteTrack**.
12. Mark `id` as the primary key and `user_id` as a foreign key.
13. Connect **User** to **FavoriteTrack** with `1-to-many`.
14. Draw an entity box for **UserPreference**.
15. Mark `id` as the primary key and `user_id` as a foreign key.
16. Connect **User** to **UserPreference** with `1-to-many`.
17. Add unique constraints for:
    `FavoriteTrack(user_id, spotify_track_id)`
    `UserPreference(user_id, emotion, spotify_track_id)`
18. Add a caption such as **Figure X. Entity Relationship Diagram of the EmoTune System**.

## Text Version of the ERD

You may use this simple reference when redrawing it:

```text
User
  PK: id
  |
  |--< PromptHistory
  |      PK: id
  |      FK: user_id
  |
  |--< ListeningSession
  |      PK: id
  |      FK: user_id
  |      FK: prompt_history_id
  |
  |--< FavoriteTrack
  |      PK: id
  |      FK: user_id
  |      UNIQUE: (user_id, spotify_track_id)
  |
  |--< UserPreference
         PK: id
         FK: user_id
         UNIQUE: (user_id, emotion, spotify_track_id)

PromptHistory
  PK: id
  FK: user_id
  |
  |--< ListeningSession
```

## Data Normalization Guide

For your documentation, explain normalization up to at least **Third Normal Form (3NF)**.

## First Normal Form (1NF)

A table is in **1NF** if:

- each row is unique
- each column stores one kind of value
- there are no repeating groups in separate columns

### EmoTune 1NF Notes

The main relational tables generally satisfy 1NF because:

- each table has a primary key
- rows are unique
- the core scalar columns such as `email`, `track_name`, `emotion`, and `listen_duration` are atomic

However, some fields are stored as JSON and are only partially normalized from a strict relational perspective:

- `spotify_granted_scopes`
- `preferred_artists`
- `emotion_scores`
- `playlist_data`
- `music_picker_data`

If your instructor expects strict 1NF in the database design chapter, mention that these are **practical JSON fields used by the current implementation**, and that a fully normalized design would split them into child tables.

## Second Normal Form (2NF)

A table is in **2NF** if:

- it is already in 1NF
- every non-key attribute depends on the full primary key

### EmoTune 2NF Notes

The current tables mostly satisfy 2NF because each table uses a single-column surrogate primary key such as `id`.

This means:

- non-key attributes depend on the whole primary key
- there are no partial dependencies caused by composite primary keys

You may still mention that `FavoriteTrack` and `UserPreference` use composite **unique constraints**, but not composite primary keys.

## Third Normal Form (3NF)

A table is in **3NF** if:

- it is already in 2NF
- non-key attributes do not depend on other non-key attributes

### EmoTune 3NF Notes

The core relational design is close to 3NF because:

- user information is separated from favorites, history, sessions, and preferences
- favorites are stored separately from listening history
- learned preferences are stored separately from raw sessions
- prompt history is stored separately from the user record

This reduces duplication and keeps the main relationships clear.

Still, some practical denormalization remains because JSON fields combine multiple pieces of structured data into one column.

Examples:

- `emotion_scores` stores many emotion-probability pairs inside one field
- `playlist_data` stores multiple recommended tracks inside one field
- `music_picker_data` stores session and recommendation metadata inside one field
- `preferred_artists` stores multiple artist values inside one field

For a stricter 3NF design, these should be separated into related tables.

## Recommended Fully Normalized Extension

If you need to present a stricter normalized design for your paper, propose these additional tables:

1. **UserPreferredArtist**
   Split `preferred_artists` into:
   - `id`
   - `user_id`
   - `artist_name`

2. **UserSpotifyScope**
   Split `spotify_granted_scopes` into:
   - `id`
   - `user_id`
   - `scope_name`

3. **PromptEmotionScore**
   Split `emotion_scores` into:
   - `id`
   - `prompt_history_id`
   - `emotion_name`
   - `score`

4. **PromptPlaylistTrack**
   Split `playlist_data` into:
   - `id`
   - `prompt_history_id`
   - `spotify_track_id`
   - `track_name`
   - `artist_name`
   - `rank_order`

5. **PromptSessionMetadata** or separate child tables
   Split `music_picker_data` into related session and recommendation tables if full normalization is required.

Important note:

- These extra tables describe a **more normalized target design**.
- They are not all separate tables in the current implementation.

## Suggested Normalization Write-Up Per Entity

You can describe each table like this:

### User

- Primary Key: `id`
- In 1NF because the core fields are atomic and each record is unique
- In 2NF because the table uses a single primary key
- Close to 3NF, but `preferred_artists` and `spotify_granted_scopes` are JSON fields and could be split into child tables for stricter normalization

### PromptHistory

- Primary Key: `id`
- Foreign Key: `user_id`
- In 1NF for the scalar fields
- In 2NF because all non-key values depend on the single primary key
- Not fully strict 3NF if JSON fields such as `emotion_scores`, `playlist_data`, and `music_picker_data` are treated as repeating structured data

### ListeningSession

- Primary Key: `id`
- Foreign Keys: `user_id`, `prompt_history_id`
- In 1NF, 2NF, and near 3NF because the columns describe one listening event record without major transitive dependency issues

### FavoriteTrack

- Primary Key: `id`
- Foreign Key: `user_id`
- Unique Constraint: `(user_id, spotify_track_id)`
- In 1NF, 2NF, and near 3NF because each row stores one favorite track per user

### UserPreference

- Primary Key: `id`
- Foreign Key: `user_id`
- Unique Constraint: `(user_id, emotion, spotify_track_id)`
- In 1NF, 2NF, and near 3NF because each record stores one learned preference unit for one user, emotion, and track

## What Not to Include in the ERD

Do not include these as database entities unless you are clearly labeling them as conceptual extensions:

- Spotify API
- Flutter screens
- BERT model
- LightFM
- admin dashboard page
- recommendation session logic

These are system components, not core stored tables.

## What Not to Claim in the Normalization Section

Do not claim that the current schema is perfectly normalized if you are showing the real implementation.

A more accurate statement is:

- the **core relational tables are normalized enough for the current application**
- some fields use **JSON-based denormalization for flexibility**
- a stricter academic design can split those JSON fields into child entities

## Suggested Figure and Table Captions

You may use captions like these:

- **Figure X. Entity Relationship Diagram of the EmoTune System**
- **Table X.X. Database Normalization for User**
- **Table X.X. Database Normalization for PromptHistory**
- **Table X.X. Database Normalization for ListeningSession**
- **Table X.X. Database Normalization for FavoriteTrack**
- **Table X.X. Database Normalization for UserPreference**

## Summary

The safest way to document the EmoTune database is:

1. build the ERD from the five real stored entities
2. show `User` as the parent entity
3. show `PromptHistory`, `ListeningSession`, `FavoriteTrack`, and `UserPreference` as related entities
4. explain that admin uses the same user table, not a separate admin table
5. explain that the core design is mostly normalized, but some JSON fields are practical denormalized structures
6. optionally propose extra child tables if your paper requires a stricter fully normalized design

That gives you an ERD and normalization section that stays faithful to the current EmoTune system while still being academically clear.
