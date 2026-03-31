# EmoTune Use Case Diagram Guide

## Purpose

This file explains how to create a **Use Case Diagram** for the EmoTune system based on the current project.

The sample picture you shared is only an example of use-case style. The actual use case diagram for EmoTune should reflect the real actors and features of this system.

## What a Use Case Diagram Shows

A use case diagram shows:

- the **actors** interacting with the system
- the **main functions** the system provides
- the **system boundary**
- the relationships between actors and use cases

Use case diagrams focus on **what the system does**, not how the internal code works.

## Difference Between Use Case Diagram and Other Diagrams

- A **context diagram** shows external entities and high-level data exchange.
- A **DFD** shows data movement between processes and data stores.
- A **flowchart** shows step-by-step control flow and decisions.
- A **use case diagram** shows actor goals and system functions.

## System Boundary

Draw one large rectangle and label it:

- **EmoTune System**

All use cases should be placed **inside** this system boundary.

All actors should be placed **outside** the system boundary.

## Recommended Actors for EmoTune

Use these actors for the current system:

1. **Guest**
   This actor represents a person who has not logged in yet.

2. **User**
   This actor represents an authenticated EmoTune user.

3. **Administrator**
   This actor represents an admin account that can access analytics and user management.

4. **Spotify API**
   This actor represents the external Spotify service used for authentication, catalog search, and playback-related support.

Important note:

- If your instructor prefers a simpler diagram, you may omit **Guest** and keep only **User**, **Administrator**, and **Spotify API**.
- If you want a more accurate user-role structure, you can show **User** as the main authenticated actor and **Guest** as the actor for registration and login.

## Main Use Cases for Guest

Place these use cases inside the system and connect them to **Guest**:

- **Register Account**
- **Log In**

You may also add:

- **Accept Terms and Privacy**

if you want to reflect the updated sign-up flow more clearly.

## Main Use Cases for User

Place these use cases inside the system and connect them to **User**:

- **Log In**
- **Analyze Mood from Text**
- **Select Emotion Directly**
- **Get Music Recommendations**
- **Choose Outcome Mode**
- **Set Taste Controls**
- **View Playlist Recommendations**
- **Play Music**
- **Control Playback**
- **Respond to Session Check-In**
- **Save Favorite Track**
- **View Favorites**
- **View History**
- **View Mood Statistics**
- **Update Profile**
- **Update Preferred Artists**
- **Connect Spotify Account**
- **Disconnect Spotify Account**

If you want a cleaner diagram, you can merge some use cases into broader ones:

- **Manage Profile**
- **Manage Favorites**
- **Manage Listening Session**

## Main Use Cases for Administrator

Place these use cases inside the system and connect them to **Administrator**:

- **Log In**
- **View Admin Dashboard**
- **View Mood Analytics**
- **View User Records**
- **Search Users**
- **Delete User Account**

You may also include:

- **Monitor Spotify Connection Statistics**
- **Review Playlist Activity Summary**

if your diagram needs to show more admin reporting features.

## Main Use Cases for Spotify API

Connect the **Spotify API** actor to the use cases that rely on Spotify services:

- **Authenticate Spotify Account**
- **Search Spotify Catalog**
- **Retrieve Track Metadata**
- **Prepare Playback**
- **Control Spotify Playback**

Important note:

- Spotify API is an external supporting actor.
- It should not be treated as a human user actor.

## Recommended Primary User Use Cases

If you want one clean central user diagram, these are the most important use cases to keep:

1. **Register Account**
2. **Log In**
3. **Analyze Mood from Text**
4. **Select Emotion Directly**
5. **Get Music Recommendations**
6. **Play Music**
7. **Respond to Session Check-In**
8. **Save Favorite Track**
9. **View History**
10. **Update Profile**
11. **Connect Spotify Account**

## Recommended Admin Use Cases

If you want a smaller separate admin use case diagram, keep these:

1. **Log In**
2. **View Admin Dashboard**
3. **View Mood Analytics**
4. **Search Users**
5. **Delete User Account**

## Suggested Include Relationships

Use `<<include>>` when one use case always needs another use case.

For EmoTune, these are good `include` relationships:

- **Register Account** `<<include>>` **Accept Terms and Privacy**
- **Analyze Mood from Text** `<<include>>` **Generate Supportive Response**
- **Get Music Recommendations** `<<include>>` **Search Spotify Catalog**
- **Get Music Recommendations** `<<include>>` **Retrieve Track Metadata**
- **Connect Spotify Account** `<<include>>` **Authenticate Spotify Account**
- **Play Music** `<<include>>` **Prepare Playback**
- **Control Playback** `<<include>>` **Control Spotify Playback**
- **View Admin Dashboard** `<<include>>` **View Mood Analytics**
- **View Admin Dashboard** `<<include>>` **View User Records**

## Suggested Extend Relationships

Use `<<extend>>` when a use case happens only under certain conditions.

For EmoTune, these are good `extend` relationships:

- **Respond to Session Check-In** `<<extend>>` **Play Music**
- **Save Favorite Track** `<<extend>>` **View Playlist Recommendations**
- **Choose Outcome Mode** `<<extend>>` **Get Music Recommendations**
- **Set Taste Controls** `<<extend>>` **Get Music Recommendations**
- **Delete User Account** `<<extend>>` **Search Users**

## Optional Actor Generalization

If your instructor wants a more formal UML structure, you may use actor generalization:

- **Guest** for account creation and login
- **User** for authenticated features
- **Administrator** as a specialized user role

If you use this version:

- connect **Administrator** to admin-only use cases
- keep normal user use cases connected to **User**
- keep registration connected to **Guest**

## Instructions for Drawing the Use Case Diagram

Follow these steps:

1. Draw one large rectangle labeled **EmoTune System**.
2. Place the actors **Guest**, **User**, **Administrator**, and **Spotify API** outside the rectangle.
3. Place the main user use cases inside the rectangle as ovals.
4. Place the admin use cases inside the rectangle as ovals on the opposite side.
5. Place Spotify-dependent use cases inside the rectangle near the right or lower side.
6. Draw association lines from each actor to the use cases they interact with.
7. Add `<<include>>` relationships where one use case always depends on another.
8. Add `<<extend>>` relationships where a behavior is conditional or optional.
9. Keep the wording short and action-based.
10. Add a caption such as **Figure X. Use Case Diagram of the EmoTune System**.

## Recommended Layout

A clean layout for EmoTune is:

- left side: **Guest** and **User**
- center: major user use cases
- right side: **Administrator**
- far right or lower right: **Spotify API**

This layout keeps user features, admin features, and external Spotify support easy to read.

## Suggested Main Diagram Structure

If you want one complete use case diagram, include these inside the system boundary:

- Register Account
- Log In
- Analyze Mood from Text
- Select Emotion Directly
- Get Music Recommendations
- Choose Outcome Mode
- Set Taste Controls
- View Playlist Recommendations
- Play Music
- Control Playback
- Respond to Session Check-In
- Save Favorite Track
- View Favorites
- View History
- View Mood Statistics
- Update Profile
- Update Preferred Artists
- Connect Spotify Account
- Disconnect Spotify Account
- View Admin Dashboard
- View Mood Analytics
- View User Records
- Search Users
- Delete User Account
- Authenticate Spotify Account
- Search Spotify Catalog
- Retrieve Track Metadata
- Prepare Playback
- Control Spotify Playback

## Recommended Simpler Version

If the full diagram becomes too crowded, simplify it to these use cases:

- Register Account
- Log In
- Analyze Mood
- Get Music Recommendations
- Play Music
- Manage Favorites
- View History
- Manage Profile
- Connect Spotify
- View Admin Dashboard
- Search Users
- Delete User Account

This version is often better for thesis or capstone documents because it is easier to read.

## What Not to Include in the Use Case Diagram

Do not include:

- database tables
- Django models
- Flutter screens
- API endpoints
- BERT model internals
- LightFM internals
- JSON fields
- technical helper functions

Those belong in technical documentation, not in a use case diagram.

## Simple Text Outline

```text
Actors:
- Guest
- User
- Administrator
- Spotify API

Guest:
- Register Account
- Log In

User:
- Log In
- Analyze Mood from Text
- Select Emotion Directly
- Get Music Recommendations
- Choose Outcome Mode
- Set Taste Controls
- View Playlist Recommendations
- Play Music
- Control Playback
- Respond to Session Check-In
- Save Favorite Track
- View Favorites
- View History
- View Mood Statistics
- Update Profile
- Update Preferred Artists
- Connect Spotify Account
- Disconnect Spotify Account

Administrator:
- Log In
- View Admin Dashboard
- View Mood Analytics
- View User Records
- Search Users
- Delete User Account

Spotify API:
- Authenticate Spotify Account
- Search Spotify Catalog
- Retrieve Track Metadata
- Prepare Playback
- Control Spotify Playback
```

## Suggested Figure Captions

You may use captions like these:

- **Figure X. Use Case Diagram of the EmoTune System**
- **Figure X.X. Use Case Diagram for User Functions**
- **Figure X.X. Use Case Diagram for Admin Functions**
- **Figure X.X. Use Case Diagram for Spotify Integration**

## Summary

The safest way to create the EmoTune use case diagram is:

1. draw one system boundary labeled **EmoTune System**
2. place **Guest**, **User**, **Administrator**, and **Spotify API** outside the boundary
3. add the main user, admin, and Spotify-related use cases inside the boundary
4. connect actors only to the use cases they directly interact with
5. use `<<include>>` and `<<extend>>` only where they make sense
6. keep the diagram readable by simplifying or splitting it into smaller diagrams when needed

That approach will give you a use case diagram that matches the current EmoTune system and follows the style of the sample you shared.
