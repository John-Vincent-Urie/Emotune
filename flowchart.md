# EmoTune Flowchart Diagram Guide

## Purpose

This file explains how to create a **flowchart diagram** for the EmoTune system based on the current project.

A flowchart shows:

- the **sequence of steps** in the system
- the **decisions** made during processing
- the **possible paths** the user or admin can follow
- the start and end of each process flow

The example images you shared are only visual references. The actual flowchart for EmoTune should follow the real system behavior of the app.

## Difference Between Flowchart, Context Diagram, and DFD

- A **context diagram** shows EmoTune as one single process with external entities.
- A **DFD** shows how data moves between processes, data stores, and external entities.
- A **flowchart** shows the step-by-step control flow of actions and decisions.

Use a flowchart when you want to explain:

- what happens first, next, and last
- where decisions are made
- how the system reacts to different conditions

## Standard Flowchart Symbols

Use these symbols when drawing the flowchart:

- **Oval**: Start or End
- **Rectangle**: Process or action
- **Diamond**: Decision
- **Parallelogram**: Input or Output
- **Connector circle**: connector to another section
- **Arrow**: direction of flow

## Main Flowchart Scope for EmoTune

The best main flowchart for EmoTune should show the user journey from entering the app up to receiving music recommendations and playback.

The major system parts to include are:

1. user authentication
2. mood input or emotion selection
3. emotion analysis
4. recommendation generation
5. playback preparation
6. listening and session tracking
7. user feedback and preference update

## Recommended Main User Flow

Use this as the primary flow for the main system flowchart:

1. **Start**
2. **Open EmoTune App**
3. **User logs in or registers**
4. **Decision: Is authentication successful?**
   Yes -> continue
   No -> show error and return to login
5. **Display Home Screen**
6. **Decision: Did the user type a mood prompt or select an emotion tab?**
   Mood prompt -> send text for analysis
   Emotion tab -> use selected emotion directly
7. **Analyze emotion or build explicit emotion result**
8. **Build supportive response**
9. **Apply outcome mode and taste controls**
10. **Retrieve recommendation candidates**
11. **Rank and filter tracks**
12. **Display recommendations**
13. **Decision: Did the user choose a track or playlist?**
    Yes -> prepare playback
    No -> end or wait for another action
14. **Start playback**
15. **Track listening activity**
16. **Decision: Is a session check-in needed?**
    Yes -> show check-in prompt
    No -> continue playback
17. **Decision: Did the user give feedback, favorite a song, or continue listening?**
    Yes -> update history and preferences
    No -> continue or end session
18. **End**

## Recommended Decision Points

The most important diamonds in the EmoTune flowchart should be:

- **Is authentication successful?**
- **Did the user enter text or choose an emotion tab?**
- **Is the text input empty?**
- **Did emotion analysis succeed?**
- **Is fallback analysis needed?**
- **Is Spotify connected?**
- **Is preview playback available?**
- **Did the user start playback?**
- **Is check-in required?**
- **Did the user feel better?**
- **Did the user enable training for this session?**
- **Did the admin request analytics or user management?**

## Suggested Main Processes for the Flowchart

Use process boxes like these:

- Open app
- Register account
- Log in user
- Validate credentials
- Receive mood input
- Analyze emotion
- Generate supportive response
- Build recommendation profile
- Query Spotify
- Rank tracks
- Display playlist
- Prepare playback
- Start song playback
- Track listening event
- Update preferences
- Save history

## Main User Flow Instructions

Follow these steps to draw the main user flowchart:

1. Start with an oval labeled **Start**.
2. Add a rectangle for **Open EmoTune App**.
3. Add a rectangle for **Login or Register**.
4. Add a diamond labeled **Authentication successful?**
5. If **No**, connect to **Show login error** and loop back to **Login or Register**.
6. If **Yes**, go to **Display Home Screen**.
7. Add a parallelogram for **Enter mood text or select emotion**.
8. Add a diamond labeled **Text input or emotion tab?**
9. If **Text input**, go to **Analyze Emotion**.
10. If **Emotion tab**, go to **Build Explicit Emotion Result**.
11. Join both paths into **Generate Supportive Response**.
12. Continue to **Apply Outcome Mode and Taste Controls**.
13. Continue to **Retrieve Spotify Candidates**.
14. Continue to **Rank and Filter Tracks**.
15. Continue to **Display Recommendations**.
16. Add a diamond labeled **User selected track?**
17. If **No**, return to **Display Recommendations** or **End**.
18. If **Yes**, continue to **Prepare Playback**.
19. Add a diamond labeled **Spotify playback available?**
20. If **Yes**, go to **Start Playback**.
21. If **No**, go to **Use preview playback** or **Show playback message**.
22. Continue to **Track Listening Event**.
23. Add a diamond labeled **Check-in needed?**
24. If **Yes**, go to **Show session prompt**.
25. Add a diamond labeled **User feels better?**
26. If **Yes**, go to **Update session state** and continue.
27. If **No**, go to **Adjust playlist/session flow** and continue.
28. Continue to **Update History and Preferences**.
29. End with an oval labeled **End**.

## Recommended Sub-Flowcharts

Instead of making one very crowded diagram, it is better to create multiple smaller flowcharts for the major parts of EmoTune.

Recommended separate flowcharts:

1. **User Authentication Flow**
2. **Emotion Analysis Flow**
3. **Music Recommendation Flow**
4. **Playback and Session Flow**
5. **Profile and Favorites Flow**
6. **Admin Flow**

## Flowchart 1: User Authentication

Use these steps:

1. Start
2. Open login/register screen
3. Enter registration or login details
4. Decision: Register or login?
5. If register:
   Create user account
   Save user record
   Return authentication result
6. If login:
   Validate credentials
   Decision: Credentials valid?
   Yes -> generate token and continue
   No -> show invalid credentials message
7. End

Important decisions:

- Register or login?
- Are required fields complete?
- Are credentials valid?

## Flowchart 2: Emotion Analysis

Use these steps:

1. Start
2. Receive user text or selected emotion
3. Decision: Is text empty?
4. If yes, show input error
5. If no, continue
6. Decision: Did the user choose an explicit emotion?
7. If yes, build explicit emotion result
8. If no, run emotion classifier
9. Decision: Did classifier succeed?
10. If no, use fallback analysis
11. If yes, continue with predicted emotion
12. Build top-emotion profile
13. Build Plutchik-compatible profile
14. Generate supportive response
15. Save prompt history
16. End

Important decisions:

- Is text empty?
- Explicit emotion or text analysis?
- Did classifier succeed?
- Is fallback needed?

## Flowchart 3: Music Recommendation

Use these steps:

1. Start
2. Receive emotion result
3. Apply outcome mode
4. Apply taste profile
5. Retrieve user context
6. Query Spotify candidates
7. Decision: Are Spotify candidates available?
8. If no, use fallback or local alternatives
9. If yes, continue
10. Rank tracks with heuristic and personalization logic
11. Build final playlist
12. Save recommendation context
13. Display playlist to user
14. End

Important decisions:

- Are Spotify candidates available?
- Is personalization data available?
- Use LightFM ranking or fallback ranking?

## Flowchart 4: Playback and Session Flow

Use these steps:

1. Start
2. User selects track
3. Prepare playback
4. Decision: Spotify remote playback available?
5. If yes, start Spotify playback
6. If no, decision: Is preview URL available?
7. If yes, start preview playback
8. If no, show playback unavailable message
9. Track listen duration
10. Update playback status on screen
11. Decision: Has the track ended?
12. If yes, move to next track
13. Decision: Is session check-in needed?
14. If yes, show check-in prompt
15. Decision: Did user feel better?
16. If yes, keep or complete session
17. If no, adjust recovery or session path
18. Save listen event
19. End

Important decisions:

- Spotify playback available?
- Preview available?
- Has track ended?
- Is check-in needed?
- Did user feel better?

## Flowchart 5: Profile and Favorites Flow

Use these steps:

1. Start
2. Open profile or favorites screen
3. Decision: Update profile, manage favorites, or update preferences?
4. If update profile:
   Validate profile data
   Save profile updates
5. If manage favorites:
   Add or remove favorite track
   Save favorite record
6. If update preferences:
   Save preferred artists
   Save personalization settings
7. Show confirmation message
8. End

Important decisions:

- Which action did the user choose?
- Is profile data valid?
- Add or remove favorite?

## Flowchart 6: Admin Flow

Use these steps:

1. Start
2. Open admin dashboard
3. Enter admin credentials
4. Decision: Admin authenticated?
5. If no, show access denied or login error
6. If yes, display admin dashboard
7. Decision: View analytics or manage users?
8. If view analytics:
   Retrieve user counts
   Retrieve mood distribution
   Display dashboard summary
9. If manage users:
   Search user records
   Decision: Delete user?
   If yes, execute deletion
   If no, continue browsing
10. Log admin action if needed
11. End

Important decisions:

- Admin authenticated?
- View analytics or manage users?
- Delete user?

## Recommended Connectors

If the full diagram becomes too large, use connector circles such as:

- `A` for authentication continuation
- `B` for emotion analysis continuation
- `C` for recommendation continuation
- `D` for playback continuation
- `E` for admin continuation

This is especially helpful if you split one big system flow into two or three pages.

## What to Avoid in the Flowchart

Do not include:

- source-code filenames
- API endpoint URLs
- class names
- model names like `AutoModelForSequenceClassification`
- database table fields
- detailed UI styling
- too many tiny technical steps

Keep the flowchart focused on system behavior, not implementation code.

## Simple Main Flow Outline

```text
Start
  -> Open EmoTune App
  -> Login or Register
  -> Authentication successful?
      No -> Show error -> Login or Register
      Yes -> Home Screen
  -> Enter mood text or select emotion
  -> Text input or emotion tab?
      Text -> Analyze Emotion
      Emotion tab -> Build Explicit Emotion Result
  -> Generate Supportive Response
  -> Apply Outcome Mode and Taste Controls
  -> Retrieve Spotify Candidates
  -> Rank and Filter Tracks
  -> Display Recommendations
  -> User selected track?
      No -> End or wait
      Yes -> Prepare Playback
  -> Spotify playback available?
      Yes -> Start Playback
      No -> Preview available?
          Yes -> Start Preview Playback
          No -> Show playback message
  -> Track Listening Event
  -> Check-in needed?
      Yes -> Show prompt -> User feels better?
      No -> Continue playback
  -> Update History and Preferences
  -> End
```

## Suggested Figure Captions

You may use captions like these:

- **Figure X. Main System Flowchart of the EmoTune System**
- **Figure X.X. Flowchart of User Authentication**
- **Figure X.X. Flowchart of Emotion Analysis**
- **Figure X.X. Flowchart of Music Recommendation**
- **Figure X.X. Flowchart of Playback and Session Tracking**
- **Figure X.X. Flowchart of Profile and Favorites Management**
- **Figure X.X. Flowchart of Admin Operations**

## Summary

The best way to document the EmoTune flowchart is:

1. create one **main system flowchart**
2. create smaller supporting flowcharts for the major features
3. use diamonds only for real decisions
4. keep the wording simple and step-based
5. make the flow reflect the real app behavior of authentication, emotion analysis, recommendation, playback, history, feedback, and admin control

That approach will give you a flowchart set that matches the current EmoTune system and also follows the style of the example diagrams you shared.
