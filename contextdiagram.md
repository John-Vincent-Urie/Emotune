# EmoTune Context Diagram Guide

## Purpose

This file explains how to draw the **context diagram** for the EmoTune system based on the current project.

A context diagram shows:

- the entire system as **one single process**
- the **external entities** that interact with the system
- the **data flows** that move in and out of the system

At this level, the diagram must stay high-level. It should not show internal parts such as BERT, LightFM, Django apps, Flutter screens, database tables, or API endpoints.

## Central Process

Place one process in the center of the diagram:

- **0 - EmoTune System**

This single process represents the whole EmoTune application, including:

- emotion analysis from user text or selected mood
- supportive response generation
- music recommendation and personalization
- Spotify search and playback integration
- user account handling
- admin monitoring and management

## External Entities

Draw these three external entities around the central process:

1. **User**
2. **Administrator**
3. **Spotify API**

These are the main actors and external services that exchange data with EmoTune.

## Data Flows Between User and EmoTune System

### User to EmoTune System

Use labels like these for the arrows going from **User** to **EmoTune System**:

- Login credentials
- Free-text mood input
- Emotion tab selection
- Playlist or session choices
- Song playback controls
- Profile update information
- Feedback on recommendations
- Favorites and listening actions

### EmoTune System to User

Use labels like these for the arrows going from **EmoTune System** back to **User**:

- Mood analysis results
- Supportive response message
- Personalized song recommendations
- Playlist results
- Playback output
- Profile or account responses
- Session progress and check-in prompts

## Data Flows Between Administrator and EmoTune System

### Administrator to EmoTune System

Use labels like these for the arrows going from **Administrator** to **EmoTune System**:

- Admin login credentials
- Account search queries
- User management actions
- Account deletion commands

### EmoTune System to Administrator

Use labels like these for the arrows going from **EmoTune System** back to **Administrator**:

- Admin authentication status
- System activity logs
- User account records
- Mood distribution reports
- Most frequently detected moods
- Realtime or summary analytics

## Data Flows Between Spotify API and EmoTune System

### EmoTune System to Spotify API

Use labels like these for the arrows going from **EmoTune System** to **Spotify API**:

- Song search queries
- Playlist retrieval requests
- Song streaming or playback requests
- API authentication requests

### Spotify API to EmoTune System

Use labels like these for the arrows going from **Spotify API** back to **EmoTune System**:

- API access tokens
- Song metadata
- Audio features
- Streaming or preview URLs
- Album artwork

## Instructions for Drawing

Follow these steps when creating the diagram:

1. Draw one process box in the center and label it **0 - EmoTune System**.
2. Place **User** on the left side of the diagram.
3. Place **Administrator** on the upper-right side.
4. Place **Spotify API** on the lower side or lower-left side.
5. Draw arrows from each external entity to the system for inputs.
6. Draw arrows from the system back to each external entity for outputs.
7. Label every arrow using short noun phrases, not long sentences.
8. Keep the labels readable and high-level.
9. Make sure the whole system is shown as only one process.
10. Add a figure caption such as **Figure X. Context Diagram of the EmoTune System**.

## What Not to Include

Do not place these inside the context diagram:

- BERT model
- LightFM
- Django
- Flutter
- database tables
- internal APIs
- admin dashboard pages
- training datasets

Those belong to lower-level diagrams such as DFD Level 1, architecture diagrams, or component diagrams.

## Recommended Layout

Use this layout for a clean presentation:

- Left side: **User**
- Center: **0 - EmoTune System**
- Upper-right: **Administrator**
- Lower area: **Spotify API**

This layout makes the three major interaction groups easy to read.

## Documentation Description

You may describe the diagram using this paragraph:

> The context diagram of EmoTune presents the system as a single process that interacts with three external entities: the User, the Administrator, and the Spotify API. The User sends login details, mood input, playback actions, and feedback to the system, while EmoTune returns emotion analysis, supportive messages, personalized playlists, and playback results. The Administrator manages accounts and monitors system activity through admin-side actions and reports. The Spotify API provides authentication, song metadata, audio features, and playback-related resources needed by the system.

## Quick Text Outline

```text
User <----> 0 - EmoTune System <----> Administrator
                    ^
                    |
                    v
                Spotify API
```

## Summary

The correct context diagram for EmoTune should show:

- one central process: **0 - EmoTune System**
- three external entities: **User**, **Administrator**, and **Spotify API**
- high-level data flows between the system and those entities only

That is the proper context-diagram scope for the current EmoTune system.
