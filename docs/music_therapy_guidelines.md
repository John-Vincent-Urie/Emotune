# Music Therapy Guidelines for EmoTune

This document gives the clinical/theoretical rationale behind what EmoTune plays for
each of the 13 detected emotions, so the mapping in
[`backend/api/spotify/constants.py`](../backend/api/spotify/constants.py)
(`EMOTION_SEARCH_PARAMS`) and the curated seed tracks in
[`docs/music.md`](music.md) can be checked against real music-therapy research
instead of intuition. It also documents where the two currently disagree, since a
therapy-adjacent app's biggest risk is quietly serving music that deepens distress
instead of easing it.

## Frameworks used

- **Iso-principle** (Altshuler, 1944): match the listener's current mood first,
  then gradually shift the music toward the target state. This is the basis for
  EmoTune's `match_mood` / `calm_me_down` split in
  [`backend/api/recommendation_session.py`](../backend/api/recommendation_session.py),
  and since the phased-blend change it is implemented as an actual arc rather
  than a single point — see "The iso-principle arc" below.
  ([Emotion Modulation through Music after Sadness Induction](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8656869/);
  [Music listening according to the iso principle, 2024](https://journals.sagepub.com/doi/10.1177/10298649231175029))
- **Circumplex model of affect** (Russell, 1980): every emotion can be placed on a
  valence (pleasant/unpleasant) x arousal (high/low energy) plane. This is the
  intended meaning behind the `min_valence` / `max_energy` / `target_tempo` fields in
  `EMOTION_SEARCH_PARAMS` — though see the Known Issues section below, because right
  now nothing actually reads those fields.
- **GEMS — Geneva Emotional Music Scale** (Zentner et al., 2008): a music-specific
  emotion vocabulary (wonder, transcendence, nostalgia, tenderness, tranquility, joy,
  power, tension, sadness) that maps onto EmoTune's own labels more naturally than
  generic valence/arousal does, especially for `nostalgic`, `romantic`, and `calm`.
- **Music-in-mood-regulation strategies** (Saarikallio & Erkkilä, 2007): people use
  music for seven distinct goals — Entertainment, Revival, Strong Sensation,
  Diversion, Discharge, Mental Work, Solace. Naming which strategy each emotion's
  mapping is aiming for is what makes a keyword/genre choice defensible instead of
  arbitrary (used per-emotion below).

## Important caveat: "catharsis" is not a blank check

The classic finding that venting anger *increases* rather than reduces it
(Bushman, 2002, punching-bag study) is about **behavioral** venting, not music. The
music-specific evidence is different: in
[Sharman & Dingle, 2015 ("Extreme Metal Music and Anger Processing")](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4439552/),
angry listeners who heard extreme music from their own playlist ended up *more*
positive, not more hostile, and their heart rate stayed matched rather than
spiking. The takeaway used below is nuanced, not a blanket rule: matching a high-
arousal negative emotion with high-arousal music is consistent with the iso-
principle's first step, **as long as the session then progresses toward calm**
rather than looping on aggressive content indefinitely — which is exactly what
`calm_me_down`'s blending is supposed to do for `angry`. The risk is dwelling, not
matching.

---

## Per-emotion guidance

Each entry: **therapeutic goal**, **regulation strategy** (Saarikallio), **target
audio qualities** (circumplex terms), and a check of whether the current
`EMOTION_SEARCH_PARAMS` / `docs/music.md` content matches that goal.

### happy
- **Goal**: sustain/extend a positive state.
- **Strategy**: Entertainment.
- **Target**: high valence, moderate-high arousal.
- **Current mapping**: `keywords: feel good, upbeat, joyful` / `genres: pop, dance,
  disco, summer` — matches. No concerns.

### sad
- **Goal**: validate the feeling first (iso-principle step 1: match, don't cheer up
  immediately — forced positivity reads as dismissive and is a known bad practice
  in grief support).
- **Strategy**: Solace.
- **Target**: low-moderate valence, low-moderate arousal, acoustic/intimate
  production (associated with felt understanding in receptive music therapy).
- **Current mapping**: `keywords: heartbreak, melancholy, ballad, acoustic` /
  `genres: acoustic, indie, singer-songwriter, piano` — matches Solace well.
  Routed to `calm_me_down`, so the session still drifts toward steadier ground
  after the initial validation. No concerns.

### angry
- **Goal**: match arousal first (validate, don't suppress), then de-escalate —
  per the caveat above, do not treat "aggressive genre" as inherently unsafe, but
  do not let a session stay there.
- **Strategy**: Discharge, but time-boxed.
- **Target**: high arousal initially, unpleasant-to-neutral valence, trending
  toward calm within the session (this is what `calm_me_down`'s blend is for).
- **Current mapping**: `keywords: rage, intense, aggressive, hard hitting` /
  `genres: metal, rock, punk, hardcore`. **Fixed**: `EMOTION_OUTCOME_MODES` routes
  `angry` to `calm_me_down`, but `angry` has no seat in `calm_me_down`'s
  `target_weights` (calm/stressed/fear/sad/mixed only) — so it previously had no
  target-side floor to compete against, and a confident enough reading (roughly
  above 0.76) could out-blend `calm` and keep the top slot, surfacing the
  aggressive/hardcore keyword set for exactly the person with the *strongest*
  anger signal. `apply_outcome_mode` (`recommendation_session.py`) now discounts
  any emotion absent from `target_weights` by `base_weight` a second time (so its
  ceiling is `base_weight**2`, ~0.18 at this mode's default 0.42/0.58 split),
  which keeps `angry` available as a secondary ranking signal without ever
  letting it outrank a real target emotion's floor. Verified in
  `api/test_outcome_routing.py` (`test_even_a_near_certain_angry_reading_never_outranks_calm`)
  up to 0.99 confidence. The same fix closes the identical gap for `depressing`
  and `lonely`, which had the same zero-weight omission.
- **docs/music.md seed tracks**: pop kiss-off/breakup songs (Olivia Rodrigo,
  Chappell Roan, GAYLE), not literal aggressive/hardcore tracks. These are
  actually a *better* match to Discharge-without-dwelling than the keyword/genre
  set in `constants.py` — no action needed there, the mismatch is one-directional
  (constants.py's fallback text search could still pull genuinely aggressive
  tracks the curated seed list would never surface).

### motivational
- **Goal**: energize / build resolve.
- **Strategy**: Revival.
- **Target**: high valence, high arousal.
- **Current mapping**: matches (`workout, hip-hop, edm, power-pop`). No concerns.

### fear
- **Goal**: ground and soothe — this is the emotional state of being afraid/
  anxious, not the horror-movie aesthetic.
- **Strategy**: Solace / Mental Work (grounding).
- **Target**: low arousal, neutral-to-positive valence, minimal harmonic tension,
  no jump-scare dynamics or startling production.
- **Current mapping in `constants.py`**: `keywords: calming, healing, steady,
  ambient, grounding` / `genres: ambient, piano, chill, classical` — this is
  correct and matches the therapeutic goal.
- **docs/music.md seed tracks — MISMATCH, flagged as the highest-priority fix**:
  the curated list for `fear` is "Bury a Friend" (Billie Eilish), "Thriller"
  (Michael Jackson), "Disturbia" (Rihanna), "Monster" (Kanye West), and "Aswang Sa
  Maynila" — i.e., songs about the *theme* of fear/horror, not music that soothes
  someone who is currently afraid. Several of these (startling production,
  minor-key tension, lyrics about being hunted/threatened) are close to the
  opposite of what someone in an anxious state needs, and directly risk deepening
  distress instead of easing it — which is the exact failure mode you flagged as
  the app's biggest danger. **This should be corrected before anyone relies on the
  `fear` category.** See the seed-track replacement in `docs/music.md`.

### depressing
- **Goal**: gentle validation without reinforcing hopelessness; this is the label
  most likely to sit near a genuine mental-health risk signal, so it's the
  strongest argument for pairing this mapping with the crisis-detection layer
  discussed separately (a low-arousal, low-valence label alone is not a reliable
  proxy for self-harm risk — the detection needs to look at the text, not the
  emotion label).
- **Strategy**: Solace.
- **Target**: low arousal, low-moderate valence, but avoid content that romanticizes
  despair or references self-harm.
- **Current mapping**: `keywords: gentle, comfort, healing, soft, acoustic` /
  `genres: acoustic, piano, indie, blues` — the *keyword/genre* framing is good.
- **docs/music.md seed tracks**: mostly consistent (Ariana Grande, FKA twigs), but
  "Nutshell" (Alice in Chains) and "Black" (Pearl Jam) sit at the heavier end —
  not unsafe on their own, but worth a listen-through pass since this is the
  category closest to a vulnerable listener. Recommend the team do a manual
  content check on this list specifically (lyrics, not just genre) before
  shipping, rather than a wholesale replacement — flagging for review, not
  rewriting unilaterally, since a therapy-adjacent decision like "which songs
  validate sadness without romanticizing despair" benefits from a second listen.

### surprising
- **Goal**: novelty/engagement, no specific regulation need (this label doesn't
  indicate distress).
- **Strategy**: Entertainment / Diversion.
- **Target**: unclear valence (that's the point), moderate-high arousal.
- **Current mapping**: fine as-is.

### stressed
- **Goal**: down-regulate arousal.
- **Strategy**: Diversion / Mental Work.
- **Target**: low-moderate arousal, neutral-positive valence, low tempo variance
  (predictable structure reduces cognitive load, which is why "focus"/"study"
  genres work here).
- **Current mapping**: `keywords: stress relief, calm, peaceful, focus,
  meditation` / `genres: ambient, chill, study, piano` — matches.
- **docs/music.md seed tracks**: mostly fine (Twenty One Pilots' "Stressed Out",
  Queen's "Under Pressure" thematically validate the feeling; iso-principle step
  1). Minor note: "Inuman Na" (Parokya ni Edgar, a drinking song) risks normalizing
  alcohol as the coping mechanism for stress — low severity, but worth swapping if
  the list gets revisited, since a therapy-oriented app shouldn't be the one
  suggesting a drink as the way to unwind.

### calm
- **Goal**: maintain steadiness.
- **Strategy**: Entertainment (sustaining a already-regulated state).
- **Target**: low arousal, moderate-positive valence.
- **Current mapping**: matches. Worth knowing for the capstone write-up: "Weightless"
  by Marconi Union (already in the `calm` seed list) is the track from the
  frequently-cited (non-peer-reviewed but widely reported) Mindlab International
  study claiming measurable anxiety reduction — a nice existing citation anchor if
  you want one for this category specifically.

### lonely
- **Goal**: solace / feeling understood, not further isolation.
- **Strategy**: Solace.
- **Target**: low-moderate arousal, low-moderate valence, intimate production.
- **Current mapping**: matches (`keywords: lonely, alone, missing you, solitude` /
  `genres: indie, acoustic, singer-songwriter, dream pop`). No concerns.

### romantic
- **Goal**: sustain a positive affiliative state.
- **Strategy**: Entertainment.
- **Target**: moderate-high valence, moderate arousal.
- **Current mapping**: fine as-is.

### nostalgic
- **Goal**: bittersweet reflection, generally a healthy/positive use of music
  (GEMS treats nostalgia as its own aesthetic emotion, not a negative one).
- **Strategy**: Mental Work / Entertainment.
- **Target**: mixed valence signals (this is expected and fine for this category).
- **Current mapping**: fine as-is.

### mixed
- **Goal**: honor genuine ambivalence rather than force a resolution — the code
  comment in `constants.py` already gets this right ("bittersweet... not a
  shuffle of happy and sad tracks").
- **Strategy**: Mental Work.
- **Target**: conflicting valence/arousal cues by design (minor key + upbeat
  tempo).
- **Current mapping**: matches. No concerns.

---

## The iso-principle arc

The iso-principle is *match, then shift*. A single fixed `target_weight` cannot
express that — it picks one point on the arc and stays there — so
`calm_me_down` now reads its weight from the session phase that
`update_session_plan_progress` already advances on every track end:

| Phase | `target_weight` | Intent |
|---|---|---|
| `settle` | 0.40 | meet the listener where they are (iso step 1) |
| `support` | 0.58 | transition |
| `close` | 0.78 | arrive at the steadier state (iso step 3) |

What that produces, for a full 13-label reading with the remainder spread:

| Reading | `settle` | `support` | `close` |
|---|---|---|---|
| angry 0.9 | angry | calm | calm |
| lonely 0.9 | lonely | calm | calm |
| sad 0.9 | sad | sad | calm |
| angry 0.4 | calm | calm | calm |

Three properties worth noting:

- **The off-target discount self-adjusts.** Because `base_weight = 1 -
  target_weight`, the `base_weight**2` ceiling on emotions with no seat in
  `target_weights` tightens automatically as the session progresses: `angry` can
  lead at `settle` (0.36 ceiling) and cannot at `close` (0.05). Matching is
  allowed; resting there is not.
- **`sad` holds its match longer than `angry`.** That falls out of `sad` having a
  seat in `target_weights` and is the right asymmetry — sad's content set is
  Solace-oriented and gentle, angry's is the escalating one.
- **The 0.90 cliff is gone.** Previously `angry` at 0.95 confidence was matched
  (via the recovery plan) and `angry` at 0.85 was not — a 0.10 swing flipped the
  whole experience. It is now a confidence gradient, and it covers all six
  distressing emotions, including `lonely` and `fear`, which the recovery plan
  never covered at all.

**`settle` is deliberately 0.40, not 0.0.** A full match would hand someone who
just said they feel hopeless a playlist that only deepens it. The shift is still
*reactive* — it needs the listener to answer a feel-better check-in — so the arc
is not guaranteed to complete. Until step 2 is guaranteed rather than prompted,
leaning toward the listener's emotion without ever fully abandoning the steadier
pull is the safer reading. **If the check-in flow is ever made optional or
removed, `settle` must move back up**, because at that point the app would only
be doing the matching half of a two-half technique.

### Not yet done: the gradient within a single playlist

The arc currently moves at *rebuild* points — a new message, or the feel-better
transition ([`views.py`](../backend/api/views.py), `feel_better_response`). Within
one playlist, every track is still fetched for a single emotion. The fuller
version builds the playlist itself as the gradient — candidates fetched at
several points from match to target, ordered so the arc plays out over the
tracks whether or not the listener ever answers a prompt. That is the change
that would make the trajectory unconditional.

---

## Content safety criteria for seed tracks

Applied to every list in `docs/music.md`. A track is a problem if it does any of
the following — note that "sad song for a sad listener" is *not* on this list,
because validation is therapeutic and sanitizing these lists into cheerfulness
would break the iso-principle's first step:

1. **Matches the literal word instead of the emotional need.** The original
   `fear` list (horror songs for an anxious listener) was the clearest case.
2. **References or romanticizes suicide, self-harm, or wanting to disappear** —
   disqualifying in any category, and most dangerous in `depressing`, `sad`,
   and `lonely`, which are the categories a struggling listener actually lands in.
3. **Normalizes a harmful coping mechanism** — drinking/substance use as the way
   to handle the feeling. This matters most in `stressed` and `depressing`, where
   the listener is looking for a way to cope and the app is implicitly endorsing
   whatever it plays.
4. **Glorifies violence** (especially in `angry`, where the listener is already
   activated and the content could model an outlet).
5. **Escalates arousal in a de-escalation category** (`fear`, `stressed`, `calm`) —
   startling production, jump-scare dynamics, aggressive builds.

### Changes made in this pass

| Category | Removed | Replaced with | Criterion |
|---|---|---|---|
| `stressed` (FIL) | "Laklak" – Teeth | "Pagtingin" – Ben&Ben | #3 — song is explicitly about chugging alcohol; a stress-relief list must not suggest drinking as the unwind |
| `stressed` (FIL) | "Inuman Na" – Parokya Ni Edgar | "Kumpas" – Moira Dela Torre | #3 — same; two of five picks in this list were drinking songs |
| `angry` (FIL) | "GATILYO" – BLKD | "Bazinga" – SB19 | #4 — title/imagery is gun-centred; replacement keeps the defiant, hard-hitting register without the violence |
| `depressing` (EN) | "I Know It's Over" – The Smiths | "Lean On Me" – Bill Withers | #2 — burial imagery and total desolation, served to the app's most vulnerable category; replacement still sits low but carries companionship (Solace) |
| `depressing` (EN) | "Nutshell" – Alice in Chains | "Fix You" – Coldplay | #2 — profound isolation/despair; replacement opens grief-acknowledging and builds, which is the iso-principle arc rather than forced cheer |
| `surprising` (FIL) | "Alapaap" – Eraserheads | "Ligaya" – Eraserheads | #3 — long-documented drug-reference controversy in PH; swap keeps the same artist and the surprising/eclectic register |

### Flagged for your review, deliberately NOT changed

I can read lyrics and reputation, but I cannot listen, and for several Filipino
tracks my confidence in the actual lyrical content is lower than the team's would
be. These are judgment calls better made by someone who knows the local catalogue:

- **`depressing` (FIL): "Pag-Ibig ay Kanibalismo II" – fitterkarma.** The title
  alone ("love is cannibalism") signals something dark, in the category where that
  matters most. Worth a lyric check against criterion #2.
- **`angry` (FIL): "Halik Sobrang Diin Pt. 2", "Bawal Sa Laro", "Kalapastangan".**
  Aggressive rap; I could not verify whether any cross into criterion #4. Note
  that the English `angry` list (pop kiss-off songs) is a notably gentler register
  than the Filipino one — worth deciding whether that asymmetry is intended.
- **`stressed` (EN): "Heavy" – Linkin Park.** The song itself is a good
  iso-principle match (it is *about* carrying too much). Kept for that reason, but
  flagging the Chester Bennington association in case you would rather not have it
  in a mental-health-adjacent app.
- **`depressing` (EN): "Black" – Pearl Jam.** Intense grief, but grief over loss
  rather than self-destruction — kept as legitimate validation. Your call.
- **`surprising` (EN): "Sicko Mode", "BOA".** Explicit-tagged; see the
  explicit-content gap below. Low therapeutic stakes (this is not a distress
  category), so this is a content-policy question, not a safety one.

### Missing control: nothing filters explicit tracks

`sanitize_recommendations` cleans track metadata but never looks at Spotify's
`explicit` flag — grep confirms it is not read anywhere. Curating `docs/music.md`
only controls the *seed* tracks; the bulk of what actually plays comes from
keyword/genre text search, which can return anything. If the app is going to be
defended as a wellbeing tool — particularly with student users — an explicit
filter on the search results is a cheaper and broader win than curating seed
lists one song at a time. Not implemented; flagging as the highest-leverage
remaining content control.

---

## Known issues

1. **FIXED — `fear` seed tracks in `docs/music.md` contradicted the therapeutic
   intent** — horror-themed songs served to someone who reports being afraid.
   Replaced; see `docs/music.md`.
2. **FIXED — `angry` (and `depressing`, `lonely`)'s blend-toward-calm could be
   bypassed at high confidence** — see the `angry` entry above for the mechanism
   and fix. Landed in `recommendation_session.py`'s `apply_outcome_mode`.
3. **`EMOTION_SEARCH_PARAMS['*']['audio_features']` is dead code** — defined per
   emotion but never read anywhere (Spotify's audio-features endpoint 403s for
   apps registered after Nov 2024, per the existing comment in
   `recommendations.py`). This isn't a safety bug — the keyword/genre text search
   these guidelines validate is what's actually running — but it's misleading to
   future readers who'll assume valence/energy targeting is enforced. Recommend
   either removing the field or adding a comment marking it aspirational/unused.
   Not changed in this pass to avoid touching working code outside this task's
   scope; flagging for a deliberate follow-up decision.
4. **No content moderation on user-submitted free text before it drives a
   recommendation** — addressed separately by the crisis-detection layer added in
   `backend/api/safety.py`, which is a distinct concern from music selection
   (detecting risk in what the *user* says, not what the *app* plays) but exists
   because of the same underlying goal: this app should never make a bad moment
   worse.

## Sources
- Altshuler, I. M. (1944) — origin of the iso-principle (cited via secondary
  sources above; original is pre-DOI).
- [Iso principle, controlled sadness-induction study (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8656869/)
- [Music listening per the iso principle modulates affective state, 2024](https://journals.sagepub.com/doi/10.1177/10298649231175029)
- [Personalised affect-regulation playlists: a pre-registered test of the iso principle](https://www.doi.org/10.1177/10298649261421187)
- [Music therapy for depression: systematic review + meta-analysis of RCTs (BJPsych Open)](https://www.cambridge.org/core/journals/bjpsych-open/article/music-therapy-for-patients-with-depression-systematic-review-and-metaanalysis-of-randomised-controlled-trials/AD9B45562D2499DCCE0D4C4B10C2287C)
- [Is music listening effective for reducing anxiety? Systematic review + meta-analysis, 2023](https://journals.sagepub.com/doi/10.1177/10298649211046979)
- Russell, J. A. (1980). A circumplex model of affect. ([overview](https://psu.pb.unizin.org/psych425/chapter/circumplex-models/))
- Zentner, M., Grandjean, D., & Scherer, K. R. (2008) — Geneva Emotional Music Scale.
- [Saarikallio & Erkkilä (2007), The role of music in adolescents' mood regulation](https://journals.sagepub.com/doi/10.1177/0305735607068889)
- [Bushman (2002), Does Venting Anger Feed or Extinguish the Flame?](https://journals.sagepub.com/doi/10.1177/0146167202289002) — the anti-catharsis finding, behavioral not musical.
- [Sharman & Dingle (2015), Extreme Metal Music and Anger Processing (Frontiers in Human Neuroscience)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4439552/) — the music-specific counter-nuance to #4.

These are a starting citation set, not exhaustive — see the search-strategy notes
in the project conversation history for how to extend this for the capstone
write-up (start from the two meta-analyses above and follow their reference/
citation lists rather than searching cold each time).
