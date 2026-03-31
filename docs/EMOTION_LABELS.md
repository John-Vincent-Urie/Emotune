# Emotion Labels

## Current Runtime Labels
These are the labels currently supported by the app and model integration:

- `happy`: joy, excitement, celebration, gratitude
- `sad`: grief, disappointment, heartbreak, loss
- `angry`: frustration, irritation, rage, resentment
- `motivational`: ambition, confidence, drive, determination
- `fear`: fear, anxiety, nervousness, dread
- `depressing`: emptiness, hopelessness, numbness, despair
- `surprising`: shock, amazement, unexpected events
- `stressed`: overload, pressure, burnout, tension
- `calm`: peace, stillness, relaxation, contentment
- `lonely`: isolation, longing, disconnection
- `romantic`: affection, intimacy, love, attraction
- `nostalgic`: memories, throwbacks, looking back
- `mixed`: overlapping or unclear emotional states

## Recommended Reduced Research Set
If the team needs a smaller label set for stronger model performance, use this reduced grouping:

- `happy`
- `sad`
- `angry`
- `fear_or_anxious`
- `calm`
- `romantic`
- `stressed`
- `neutral_or_mixed`

Suggested merges:

- `depressing -> sad`
- `fear -> fear_or_anxious`
- `surprising -> neutral_or_mixed`
- `lonely -> neutral_or_mixed`
- `nostalgic -> neutral_or_mixed`
- `mixed -> neutral_or_mixed`

## Example Prompts

- `happy`: "I got accepted into my dream university."
- `sad`: "Everything reminds me of what I have lost."
- `angry`: "I am so frustrated that they lied to me."
- `motivational`: "I am ready to push through and finish this."
- `fear`: "I am nervous about tomorrow's interview."
- `depressing`: "Nothing feels meaningful right now."
- `surprising`: "I still cannot believe that happened today."
- `stressed`: "I have too many deadlines and no time."
- `calm`: "I feel peaceful sitting by the ocean."
- `lonely`: "Even in a crowd I feel alone."
- `romantic`: "Being with them makes everything feel lighter."
- `nostalgic`: "That song took me right back to childhood."
- `mixed`: "I am proud but also scared about what comes next."
