# EmoTune Data Flow Diagram Guide

## Purpose

This file explains how to create the **Data Flow Diagram (DFD)** for the EmoTune system based on the current project.

A DFD shows:

- the major **processes** inside the system
- the **external entities** interacting with the system
- the **data stores** where information is saved
- the **data flows** moving between them

The example pictures you shared are only references for style and structure. The actual DFD for EmoTune should follow the real features and backend flow of this system.

## Difference Between Context Diagram and DFD

- The **context diagram** shows EmoTune as one single process.
- The **DFD Level 1** breaks EmoTune into its main internal processes.
- Lower-level DFDs such as **Diagram 2**, **Diagram 3**, and **Diagram 4** break one major process into smaller subprocesses.

If you need the context-diagram version, use [contextdiagram.md](/c:/Users/Urie/Documents/CApstone!/EmoTune-Capstone_project/contextdiagram.md#L1).

## Basic Symbols

Use the standard DFD symbols:

- **External Entity**: square or rectangle
- **Process**: rounded rectangle or process box
- **Data Store**: open-ended rectangle or parallel-line store
- **Data Flow**: arrow with a label

## Rules When Drawing

Follow these rules while making the DFD:

1. Use **verb phrases** for process names.
2. Use **noun phrases** for data-flow labels.
3. Use **noun phrases** for data-store names.
4. Number processes clearly such as `1.0`, `2.0`, `3.0`.
5. Balance the diagrams.
   The inputs and outputs of a child diagram should match the parent process it expands.
6. Do not draw program code, Flutter widgets, Django files, or machine-learning libraries as DFD objects.
7. Do not use flowchart decision diamonds in a DFD.
8. Keep the wording high-level and system-focused.

## External Entities for EmoTune

Use these external entities in the EmoTune DFD:

1. **User**
2. **Administrator**
3. **Spotify API**

## Main Data Stores in EmoTune

These are the best data stores to show based on the current system:

- **D1 User Database**
  Contains user accounts, profile information, Spotify connection fields, and personalization consent.
- **D2 Prompt History Database**
  Contains prompt text, detected emotion, confidence, AI response, playlist data, and session metadata.
- **D3 Favorite Tracks Database**
  Contains the user's saved favorite songs.
- **D4 Listening Sessions Database**
  Contains listening duration, completed session data, and prompt-linked playback records.
- **D5 User Preferences Database**
  Contains learned music preferences per user, emotion, and track.

Note:

- The current admin dashboard mostly reads from existing user and history records.
- There is no separate permanent analytics database in the current implementation, so avoid inventing a data store unless your instructor specifically wants one.

## Recommended DFD Level 1 for EmoTune

For the main DFD Level 1, break the EmoTune System into these major processes:

1. **1.0 User Authentication**
2. **2.0 Emotion Analysis**
3. **3.0 Music Recommendation**
4. **4.0 Playback and Session Tracking**
5. **5.0 User Profile and Preference Management**
6. **6.0 Admin Analytics and Dashboard**
7. **7.0 Admin User Management**
8. **8.0 Spotify Integration**

## Suggested Level 1 Data Flows

### User and 1.0 User Authentication

- User -> 1.0 User Authentication: Login credentials
- 1.0 User Authentication -> User: Authentication status
- 1.0 User Authentication <-> D1 User Database: User account data

### User and 2.0 Emotion Analysis

- User -> 2.0 Emotion Analysis: Free-text mood input
- User -> 2.0 Emotion Analysis: Emotion tab selection
- 2.0 Emotion Analysis -> User: Detected emotion
- 2.0 Emotion Analysis -> User: Supportive response
- 2.0 Emotion Analysis -> D2 Prompt History Database: Emotion result and prompt record

### 2.0 Emotion Analysis to 3.0 Music Recommendation

- 2.0 Emotion Analysis -> 3.0 Music Recommendation: Emotion profile
- 2.0 Emotion Analysis -> 3.0 Music Recommendation: Top emotions
- 2.0 Emotion Analysis -> 3.0 Music Recommendation: Outcome mode and taste profile

### 3.0 Music Recommendation and Stored Data

- 3.0 Music Recommendation <-> D3 Favorite Tracks Database: Favorite-track data
- 3.0 Music Recommendation <-> D4 Listening Sessions Database: Listening history
- 3.0 Music Recommendation <-> D5 User Preferences Database: Preference signals
- 3.0 Music Recommendation -> 8.0 Spotify Integration: Search and recommendation requests
- 8.0 Spotify Integration -> 3.0 Music Recommendation: Track metadata and candidate songs
- 3.0 Music Recommendation -> User: Recommended songs and playlist results
- 3.0 Music Recommendation -> D2 Prompt History Database: Playlist data and recommendation context

### 4.0 Playback and Session Tracking

- User -> 4.0 Playback and Session Tracking: Song selection
- User -> 4.0 Playback and Session Tracking: Playback controls
- 4.0 Playback and Session Tracking -> 8.0 Spotify Integration: Playback preparation request
- 8.0 Spotify Integration -> 4.0 Playback and Session Tracking: Playback resource or control result
- 4.0 Playback and Session Tracking -> D4 Listening Sessions Database: Listen event data
- 4.0 Playback and Session Tracking -> D5 User Preferences Database: Updated listening preferences
- 4.0 Playback and Session Tracking -> D2 Prompt History Database: Session progress and check-in result
- 4.0 Playback and Session Tracking -> User: Playback updates and session check-in prompts

### 5.0 User Profile and Preference Management
  
- User -> 5.0 User Profile and Preference Management: Profile update information
- User -> 5.0 User Profile and Preference Management: Favorite actions
- User -> 5.0 User Profile and Preference Management: Preferred artist updates
- 5.0 User Profile and Preference Management <-> D1 User Database: Profile data
- 5.0 User Profile and Preference Management <-> D3 Favorite Tracks Database: Favorite-track data
- 5.0 User Profile and Preference Management <-> D5 User Preferences Database: Preference data
- 5.0 User Profile and Preference Management -> User: Updated account and preference data

### 6.0 Admin Analytics and Dashboard

- Administrator -> 6.0 Admin Analytics and Dashboard: Admin login credentials
- Administrator -> 6.0 Admin Analytics and Dashboard: Analytics request
- 6.0 Admin Analytics and Dashboard <-> D1 User Database: User records
- 6.0 Admin Analytics and Dashboard <-> D2 Prompt History Database: Mood history data
- 6.0 Admin Analytics and Dashboard -> Administrator: Mood distribution reports
- 6.0 Admin Analytics and Dashboard -> Administrator: Monthly playlist counts
- 6.0 Admin Analytics and Dashboard -> Administrator: User summary data

### 7.0 Admin User Management

- Administrator -> 7.0 Admin User Management: Account search queries
- Administrator -> 7.0 Admin User Management: User deletion commands
- 7.0 Admin User Management <-> D1 User Database: User account records
- 7.0 Admin User Management -> Administrator: Search results
- 7.0 Admin User Management -> Administrator: Action confirmation

### 8.0 Spotify Integration

- 3.0 Music Recommendation -> 8.0 Spotify Integration: Track search request
- 4.0 Playback and Session Tracking -> 8.0 Spotify Integration: Playback command
- 5.0 User Profile and Preference Management -> 8.0 Spotify Integration: Spotify connect or disconnect request
- 8.0 Spotify Integration -> Spotify API: API authentication request
- 8.0 Spotify Integration -> Spotify API: Search request
- 8.0 Spotify Integration -> Spotify API: Playback request
- Spotify API -> 8.0 Spotify Integration: Access tokens
- Spotify API -> 8.0 Spotify Integration: Track metadata
- Spotify API -> 8.0 Spotify Integration: Audio features
- Spotify API -> 8.0 Spotify Integration: Streaming or preview data

## Suggested Child Diagrams

After creating the Level 1 DFD, you can expand the most important processes into separate diagrams.

## Diagram 2: Emotion Analysis

Recommended subprocesses:

1. **2.1 Receive User Emotion Input**
2. **2.2 Classify Emotion**
3. **2.3 Build Emotion Profile**
4. **2.4 Generate Supportive Response**
5. **2.5 Save Analysis Result**

Suggested flows:

- User -> 2.1 Receive User Emotion Input: Free-text input
- User -> 2.1 Receive User Emotion Input: Emotion selection
- 2.1 Receive User Emotion Input -> 2.2 Classify Emotion: Cleaned mood text
- 2.2 Classify Emotion -> 2.3 Build Emotion Profile: Emotion scores
- 2.3 Build Emotion Profile -> 2.4 Generate Supportive Response: Primary emotion
- 2.3 Build Emotion Profile -> 3.0 Music Recommendation: Emotion profile
- 2.4 Generate Supportive Response -> User: Supportive message
- 2.5 Save Analysis Result -> D2 Prompt History Database: Prompt and analysis record

Notes for this diagram:

- `Classify Emotion` represents the BERT-first classifier with fallback logic.
- `Build Emotion Profile` can include top emotions, confidence, and Plutchik-compatible mapping.
- Do not draw Hugging Face, PyTorch, or BERT as separate external entities.

## Diagram 3: Music Recommendation

Recommended subprocesses:

1. **3.1 Receive Emotion Profile**
2. **3.2 Retrieve User Context**
3. **3.3 Query Spotify Candidates**
4. **3.4 Rank and Filter Tracks**
5. **3.5 Build Playlist Result**
6. **3.6 Save Recommendation Context**

Suggested flows:

- 2.0 Emotion Analysis -> 3.1 Receive Emotion Profile: Emotion result
- D3 Favorite Tracks Database -> 3.2 Retrieve User Context: Favorite songs
- D4 Listening Sessions Database -> 3.2 Retrieve User Context: Listening history
- D5 User Preferences Database -> 3.2 Retrieve User Context: Preference signals
- 3.2 Retrieve User Context -> 3.3 Query Spotify Candidates: Search parameters
- 3.3 Query Spotify Candidates -> 8.0 Spotify Integration: Search request
- 8.0 Spotify Integration -> 3.3 Query Spotify Candidates: Candidate tracks
- 3.3 Query Spotify Candidates -> 3.4 Rank and Filter Tracks: Raw candidate list
- 3.2 Retrieve User Context -> 3.4 Rank and Filter Tracks: User context
- 3.4 Rank and Filter Tracks -> 3.5 Build Playlist Result: Ranked tracks
- 3.5 Build Playlist Result -> User: Playlist and recommended songs
- 3.6 Save Recommendation Context -> D2 Prompt History Database: Playlist data

Notes for this diagram:

- `Rank and Filter Tracks` represents heuristic ranking plus LightFM re-ranking when available.
- Outcome mode, session plan, and taste profile can be shown as incoming data to `3.4 Rank and Filter Tracks` or `3.5 Build Playlist Result`.

## Diagram 4: Playback and Session Tracking

Recommended subprocesses:

1. **4.1 Receive Playback Command**
2. **4.2 Request Playback Resource**
3. **4.3 Initialize Playback**
4. **4.4 Track Listening Event**
5. **4.5 Update Session Progress**
6. **4.6 Return Playback Status**

Suggested flows:

- User -> 4.1 Receive Playback Command: Song selection
- User -> 4.1 Receive Playback Command: Playback controls
- 4.1 Receive Playback Command -> 4.2 Request Playback Resource: Selected track data
- 4.2 Request Playback Resource -> 8.0 Spotify Integration: Prepare playback request
- 8.0 Spotify Integration -> 4.2 Request Playback Resource: Playback data
- 4.3 Initialize Playback -> User: Song playback
- 4.4 Track Listening Event -> D4 Listening Sessions Database: Listen duration
- 4.4 Track Listening Event -> D5 User Preferences Database: Updated preference signals
- 4.5 Update Session Progress -> D2 Prompt History Database: Session progress
- 4.5 Update Session Progress -> User: Check-in prompt or progress update
- 4.6 Return Playback Status -> User: Playback status

Notes for this diagram:

- This diagram covers preview playback, Spotify background playback, next-track handling, and session check-ins at a high level.
- Do not draw the player widget, seek bar, or phone UI components as separate processes.

## Diagram 5: User Profile and Preference Management

Recommended subprocesses:

1. **5.1 Validate Profile Input**
2. **5.2 Update User Record**
3. **5.3 Manage Favorite Tracks**
4. **5.4 Update Preferred Artists**
5. **5.5 Save Preference Settings**
6. **5.6 Confirm Profile Changes**

Suggested flows:

- User -> 5.1 Validate Profile Input: Profile update information
- 5.2 Update User Record <-> D1 User Database: User profile data
- User -> 5.3 Manage Favorite Tracks: Favorite add or remove request
- 5.3 Manage Favorite Tracks <-> D3 Favorite Tracks Database: Favorite-track data
- User -> 5.4 Update Preferred Artists: Preferred artist list
- 5.4 Update Preferred Artists <-> D1 User Database: Artist preference data
- User -> 5.5 Save Preference Settings: Personalization settings
- 5.5 Save Preference Settings <-> D1 User Database: Consent and Spotify-link data
- 5.6 Confirm Profile Changes -> User: Updated profile result

## Diagram 6: Admin Analytics and Dashboard

Recommended subprocesses:

1. **6.1 Authenticate Admin**
2. **6.2 Retrieve User Records**
3. **6.3 Compute Mood Analytics**
4. **6.4 Compile Dashboard Summary**
5. **6.5 Return Dashboard Results**

Suggested flows:

- Administrator -> 6.1 Authenticate Admin: Admin login credentials
- 6.1 Authenticate Admin -> Administrator: Admin authentication status
- 6.2 Retrieve User Records <-> D1 User Database: User account data
- 6.3 Compute Mood Analytics <-> D2 Prompt History Database: Mood history
- 6.4 Compile Dashboard Summary -> Administrator: Dashboard analytics
- 6.5 Return Dashboard Results -> Administrator: User summary and mood reports

Notes for this diagram:

- The current admin dashboard computes totals and mood distributions from existing records.
- If your adviser wants a separate analytics store, mention that it is conceptual and not a separate persistent table in the current app.

## Diagram 7: Admin User Management

Recommended subprocesses:

1. **7.1 Process Search Query**
2. **7.2 Display User Results**
3. **7.3 Execute User Deletion**
4. **7.4 Return Action Confirmation**

Suggested flows:

- Administrator -> 7.1 Process Search Query: Account search query
- 7.1 Process Search Query <-> D1 User Database: User records
- 7.2 Display User Results -> Administrator: Search results
- Administrator -> 7.3 Execute User Deletion: Deletion command
- 7.3 Execute User Deletion <-> D1 User Database: User record deletion
- 7.4 Return Action Confirmation -> Administrator: Action confirmation

## Recommended Numbering Style

Use this numbering pattern:

- Level 1 processes: `1.0`, `2.0`, `3.0`, `4.0`
- Child processes: `2.1`, `2.2`, `2.3` under process `2.0`
- Data stores: `D1`, `D2`, `D3`, `D4`, `D5`

## What Not to Put in the DFD

Do not include:

- source-code filenames
- class names
- serializers
- Flutter pages
- REST endpoint paths
- Python libraries
- direct SQL details
- UI buttons as separate processes

Those belong in implementation documentation, not in a DFD.

## Simple Level 1 Text Outline

```text
User -> 1.0 User Authentication -> D1 User Database
User -> 2.0 Emotion Analysis -> D2 Prompt History Database
2.0 Emotion Analysis -> 3.0 Music Recommendation
3.0 Music Recommendation <-> D3 Favorite Tracks Database
3.0 Music Recommendation <-> D4 Listening Sessions Database
3.0 Music Recommendation <-> D5 User Preferences Database
3.0 Music Recommendation -> 8.0 Spotify Integration <-> Spotify API
User -> 4.0 Playback and Session Tracking -> D4 Listening Sessions Database
User -> 5.0 User Profile and Preference Management <-> D1 User Database
Administrator -> 6.0 Admin Analytics and Dashboard <-> D1/D2
Administrator -> 7.0 Admin User Management <-> D1
```

## Suggested Figure Captions

You may use captions like these:

- **Figure X. Data Flow Diagram Level 1 of the EmoTune System**
- **Figure X.X. Diagram 2 - Emotion Analysis**
- **Figure X.X. Diagram 3 - Music Recommendation**
- **Figure X.X. Diagram 4 - Playback and Session Tracking**
- **Figure X.X. Diagram 5 - User Profile and Preference Management**
- **Figure X.X. Diagram 6 - Admin Analytics and Dashboard**
- **Figure X.X. Diagram 7 - Admin User Management**

## Summary

The EmoTune DFD should be built in layers:

1. Start with the context diagram.
2. Create the **Level 1 DFD** using the eight main processes.
3. Expand the most important processes into child diagrams.
4. Keep the flows balanced across diagrams.
5. Show only real system data movement, not code structure.

That approach will give you a DFD set that matches the current EmoTune system and also fits the style of the example diagrams you shared.
