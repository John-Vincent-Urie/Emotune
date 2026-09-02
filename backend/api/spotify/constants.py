"""
Spotify constants and curated seed-track / query-profile data.

Split out of the former monolithic spotify_service.py so the large,
mostly-static data tables don't crowd out the service logic that actually
changes.
"""
import re
from pathlib import Path
from django.conf import settings
import logging

logger = logging.getLogger('api.spotify_service')

SUPPORTED_SPOTIFY_ITEM_TYPES = {
    'track',
    'playlist',
    'album',
    'artist',
    'episode',
    'show',
}

SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE = 'https://api.spotify.com/v1'

MUSIC_PICKER_DOC_EMOTIONS = {
    'happy',
    'sad',
    'angry',
    'motivational',
    'fear',
    'depressing',
    'surprising',
    'stressed',
    'calm',
    'lonely',
    'romantic',
    'nostalgic',
}
MUSIC_PICKER_DOC_SEED_SOURCE = 'music_doc'


def _normalize_music_picker_emotion(value):
    normalized = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')
    return {
        'depressed': 'depressing',
    }.get(normalized, normalized)


def _music_picker_doc_path():
    configured_path = str(getattr(settings, 'MUSIC_PICKER_PLAYLIST_DOC', '') or '').strip()
    project_root = getattr(settings, 'PROJECT_ROOT', None)
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute() and project_root:
            return Path(project_root) / path
        return path

    if project_root:
        return Path(project_root) / 'docs' / 'music.md'

    return Path(__file__).resolve().parents[2] / 'docs' / 'music.md'


def _dedupe_seed_tracks(seed_tracks):
    deduped = []
    seen_keys = set()
    for seed in seed_tracks or []:
        if not isinstance(seed, dict):
            continue
        track = ' '.join(str(seed.get('track') or '').strip().split())
        artist = ' '.join(str(seed.get('artist') or '').strip().split())
        if not track or not artist:
            continue
        key = (track.lower(), artist.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        normalized_seed = {'track': track, 'artist': artist}
        if seed.get('source'):
            normalized_seed['source'] = str(seed.get('source')).strip()
        deduped.append(normalized_seed)
    return deduped


def _load_music_picker_doc_seed_tracks():
    """Load emotion playlists from docs/music.md for exact Spotify seed searches."""
    doc_path = _music_picker_doc_path()
    try:
        lines = doc_path.read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeDecodeError) as error:
        logger.warning(
            "Could not load music picker playlist document from %s: %s",
            doc_path,
            error,
        )
        return {}

    playlists = {}
    current_emotion = None
    track_pattern = re.compile(
        '^\\s*\\d+\\.\\s*"(?P<track>[^"]+)"\\s+(?:[-\\u2013\\u2014])\\s+'
        '(?P<artist>.+?)\\s*$'
    )

    for raw_line in lines:
        line = str(raw_line or '').strip()
        if not line:
            continue

        normalized_emotion = _normalize_music_picker_emotion(line)
        if normalized_emotion in MUSIC_PICKER_DOC_EMOTIONS:
            current_emotion = normalized_emotion
            playlists.setdefault(current_emotion, [])
            continue

        if current_emotion is None:
            continue

        match = track_pattern.match(line)
        if not match:
            continue

        playlists[current_emotion].append({
            'track': match.group('track'),
            'artist': match.group('artist'),
            'source': MUSIC_PICKER_DOC_SEED_SOURCE,
        })

    return {
        emotion: seed_tracks
        for emotion, seed_tracks in (
            (emotion, _dedupe_seed_tracks(seed_tracks))
            for emotion, seed_tracks in playlists.items()
        )
        if seed_tracks
    }

# Emotion to Spotify search mapping
EMOTION_SEARCH_PARAMS = {
    'happy': {
        'keywords': ['feel good', 'upbeat', 'joyful', 'sunshine', 'celebration'],
        'audio_features': {'min_valence': 0.6, 'min_energy': 0.5, 'target_tempo': 120},
        'genres': ['pop', 'dance', 'disco', 'summer'],
    },
    'sad': {
        'keywords': ['heartbreak', 'melancholy', 'emotional', 'ballad', 'acoustic'],
        'audio_features': {'max_valence': 0.4, 'max_energy': 0.5},
        'genres': ['acoustic', 'indie', 'singer-songwriter', 'piano'],
    },
    'angry': {
        'keywords': ['rage', 'intense', 'aggressive', 'powerful', 'hard hitting'],
        'audio_features': {'min_energy': 0.7, 'max_valence': 0.5, 'target_loudness': -5},
        'genres': ['metal', 'rock', 'punk', 'hardcore'],
    },
    'motivational': {
        'keywords': ['motivational', 'victory', 'champion', 'stronger', 'rise up'],
        'audio_features': {'min_energy': 0.7, 'min_valence': 0.5},
        'genres': ['workout', 'hip-hop', 'edm', 'power-pop'],
    },
    'fear': {
        'keywords': ['calming', 'healing', 'steady', 'ambient', 'grounding'],
        'audio_features': {'max_valence': 0.4, 'target_mode': 0},
        'genres': ['ambient', 'piano', 'chill', 'classical'],
    },
    'depressing': {
        'keywords': ['gentle', 'comfort', 'healing', 'soft', 'acoustic'],
        'audio_features': {'max_valence': 0.3, 'max_energy': 0.4},
        'genres': ['acoustic', 'piano', 'indie', 'blues'],
    },
    'surprising': {
        'keywords': ['unexpected', 'eclectic', 'genre bending', 'fresh', 'experimental'],
        'audio_features': {'target_valence': 0.6},
        'genres': ['indie', 'alternative', 'experimental', 'electronic'],
    },
    'stressed': {
        'keywords': ['stress relief', 'calm', 'peaceful', 'focus', 'meditation'],
        'audio_features': {'max_energy': 0.5, 'max_tempo': 100, 'target_valence': 0.5},
        'genres': ['ambient', 'chill', 'study', 'piano'],
    },
    'calm': {
        'keywords': ['calm', 'peaceful', 'ambient', 'soft piano', 'relaxing'],
        'audio_features': {'max_energy': 0.4, 'max_tempo': 90, 'min_valence': 0.4},
        'genres': ['ambient', 'chill', 'classical', 'piano'],
    },
    'lonely': {
        'keywords': ['lonely', 'alone', 'missing you', 'late night', 'solitude'],
        'audio_features': {'max_valence': 0.5, 'max_energy': 0.5},
        'genres': ['indie', 'acoustic', 'singer-songwriter', 'dream pop'],
    },
    'romantic': {
        'keywords': ['love', 'romantic', 'slow dance', 'sweet', 'affection'],
        'audio_features': {'min_valence': 0.5, 'target_energy': 0.5},
        'genres': ['r-n-b', 'soul', 'pop', 'love songs'],
    },
    'nostalgic': {
        'keywords': ['nostalgic', 'retro', 'throwback', 'memories', 'classic'],
        'audio_features': {'target_valence': 0.5},
        'genres': ['oldies', '80s', '90s', 'retro', 'classic'],
    },
    'mixed': {
        'keywords': ['diverse', 'variety', 'mix', 'playlist', 'popular'],
        'audio_features': {},
        'genres': ['pop', 'indie', 'hip-hop', 'rock'],
    },
}

def _seed_tracks(*pairs):
    return [
        {'track': track, 'artist': artist}
        for track, artist in pairs
    ]


HAPPY_SEED_TRACKS = _seed_tracks(
    ("Happy", "Pharrell Williams"),
    ("Walking on Sunshine", "Katrina & The Waves"),
    ("Good as Hell", "Lizzo"),
    ("Can't Stop the Feeling!", "Justin Timberlake"),
    ("Best Day Of My Life", "American Authors"),
    ("I Gotta Feeling", "Black Eyed Peas"),
    ("Shake It Off", "Taylor Swift"),
    ("Levitating", "Dua Lipa"),
    ("Firework", "Katy Perry"),
    ("Uptown Funk", "Mark Ronson"),
    ("On Top Of The World", "Imagine Dragons"),
    ("Good Time", "Owl City"),
    ("Pocketful of Sunshine", "Natasha Bedingfield"),
    ("September", "Earth, Wind & Fire"),
    ("Dancing Queen", "ABBA"),
    ("Three Little Birds", "Bob Marley & The Wailers"),
    ("Lovely Day", "Bill Withers"),
    ("Valerie", "Mark Ronson"),
    ("Can't Take My Eyes Off You", "Frankie Valli"),
    ("Sunroof", "Nicky Youre"),
    ("Roar", "Katy Perry"),
    ("Stronger (What Doesn't Kill You)", "Kelly Clarkson"),
    ("Mr. Blue Sky", "Electric Light Orchestra"),
    ("Cake By The Ocean", "DNCE"),
    ("Treasure", "Bruno Mars"),
    ("24K Magic", "Bruno Mars"),
    ("Don't Stop Me Now", "Queen"),
    ("Good Vibrations", "The Beach Boys"),
    ("I Want You Back", "Jackson 5"),
    ("Send Me On My Way", "Rusted Root"),
    ("Love On Top", "Beyonce"),
    ("Ain't No Mountain High Enough", "Marvin Gaye & Tammi Terrell"),
    ("Sunday Best", "Surfaces"),
    ("Island In The Sun", "Weezer"),
    ("Feel It Still", "Portugal. The Man"),
    ("Adventure Of A Lifetime", "Coldplay"),
    ("All Star", "Smash Mouth"),
    ("Beautiful Day", "U2"),
    ("Rather Be", "Clean Bandit"),
    ("Dynamite", "BTS"),
    ("Shut Up and Dance", "WALK THE MOON"),
    ("Hallucinate", "Dua Lipa"),
    ("I Wanna Dance with Somebody", "Whitney Houston"),
    ("Here Comes The Sun", "The Beatles"),
    ("I Got You (I Feel Good)", "James Brown"),
    ("Unwritten", "Natasha Bedingfield"),
    ("Celebration", "Kool & The Gang"),
    ("This Will Be (An Everlasting Love)", "Natalie Cole"),
    ("Good Life", "OneRepublic"),
    ("Watermelon Sugar", "Harry Styles"),
)

SAD_SEED_TRACKS = _seed_tracks(
    ("Someone You Loved", "Lewis Capaldi"),
    ("All I Want", "Kodaline"),
    ("Let Her Go", "Passenger"),
    ("Someone Like You", "Adele"),
    ("The Night We Met", "Lord Huron"),
    ("Another Love", "Tom Odell"),
    ("Liability", "Lorde"),
    ("Skinny Love", "Bon Iver"),
    ("Before You Go", "Lewis Capaldi"),
    ("When We Were Young", "Adele"),
    ("The Scientist", "Coldplay"),
    ("Fix You", "Coldplay"),
    ("I Can't Make You Love Me", "Bonnie Raitt"),
    ("Jealous", "Labrinth"),
    ("When I Was Your Man", "Bruno Mars"),
    ("Easy On Me", "Adele"),
    ("Love In The Dark", "Adele"),
    ("Say You Love Me", "Jessie Ware"),
    ("Everybody Hurts", "R.E.M."),
    ("How to Save a Life", "The Fray"),
    ("Chasing Cars", "Snow Patrol"),
    ("All Too Well", "Taylor Swift"),
    ("Back To December", "Taylor Swift"),
    ("drivers license", "Olivia Rodrigo"),
    ("Jar Of Hearts", "Christina Perri"),
    ("Un-break My Heart", "Toni Braxton"),
    ("Breathe Me", "Sia"),
    ("Youth", "Daughter"),
    ("Almost Lover", "A Fine Frenzy"),
    ("Hurt", "Johnny Cash"),
    ("Landslide", "Fleetwood Mac"),
    ("To Build A Home", "The Cinematic Orchestra"),
    ("Lost Without You", "Freya Ridings"),
    ("Say Something", "A Great Big World"),
    ("Falling", "Harry Styles"),
    ("Wicked Game", "Chris Isaak"),
    ("Nothing Compares 2 U", "Sinead O'Connor"),
    ("No Surprises", "Radiohead"),
    ("Supermarket Flowers", "Ed Sheeran"),
    ("She Used To Be Mine", "Sara Bareilles"),
    ("Slow Dancing In A Burning Room", "John Mayer"),
    ("Arcade", "Duncan Laurence"),
    ("everything i wanted", "Billie Eilish"),
    ("ghostin", "Ariana Grande"),
    ("if the world was ending", "JP Saxe"),
    ("Stay", "Rihanna"),
    ("Because Of You", "Kelly Clarkson"),
    ("Broken", "Seether"),
    ("Memories", "Conan Gray"),
    ("River", "Joni Mitchell"),
)

ANGRY_SEED_TRACKS = _seed_tracks(
    ("Killing In The Name", "Rage Against The Machine"),
    ("Break Stuff", "Limp Bizkit"),
    ("Duality", "Slipknot"),
    ("Bodies", "Drowning Pool"),
    ("Down With The Sickness", "Disturbed"),
    ("Chop Suey!", "System Of A Down"),
    ("Given Up", "Linkin Park"),
    ("One Step Closer", "Linkin Park"),
    ("Psychosocial", "Slipknot"),
    ("Bulls On Parade", "Rage Against The Machine"),
    ("Last Resort", "Papa Roach"),
    ("Sabotage", "Beastie Boys"),
    ("Before I Forget", "Slipknot"),
    ("Headstrong", "Trapt"),
    ("Dragula", "Rob Zombie"),
    ("Prayer Of The Refugee", "Rise Against"),
    ("Animal I Have Become", "Three Days Grace"),
    ("Riot", "Three Days Grace"),
    ("I Hate Everything About You", "Three Days Grace"),
    ("The Way I Am", "Eminem"),
    ("X Gon' Give It To Ya", "DMX"),
    ("DNA.", "Kendrick Lamar"),
    ("Black Skinhead", "Kanye West"),
    ("B.Y.O.B.", "System Of A Down"),
    ("Walk", "Pantera"),
    ("Surfacing", "Slipknot"),
    ("People = Shit", "Slipknot"),
    ("Spit It Out", "Slipknot"),
    ("Freak On A Leash", "Korn"),
    ("Coming Undone", "Korn"),
    ("Indestructible", "Disturbed"),
    ("Ten Thousand Fists", "Disturbed"),
    ("Nightmare", "Avenged Sevenfold"),
    ("The Pretender", "Foo Fighters"),
    ("My Own Summer (Shove It)", "Deftones"),
    ("Numb", "Linkin Park"),
    ("Bleed It Out", "Linkin Park"),
    ("Faint", "Linkin Park"),
    ("The Kill (Bury Me)", "Thirty Seconds To Mars"),
    ("Misery Business", "Paramore"),
    ("You Oughta Know", "Alanis Morissette"),
    ("Ace Of Spades", "Motorhead"),
    ("Paranoid", "Black Sabbath"),
    ("Master Of Puppets", "Metallica"),
    ("Battery", "Metallica"),
    ("Enter Sandman", "Metallica"),
    ("Smells Like Teen Spirit", "Nirvana"),
    ("Du Hast", "Rammstein"),
    ("Face Down", "The Red Jumpsuit Apparatus"),
    ("Monster", "Skillet"),
)

MOTIVATIONAL_SEED_TRACKS = _seed_tracks(
    ("Lose Yourself", "Eminem"),
    ("Hall of Fame", "The Script"),
    ("Stronger", "Kanye West"),
    ("Eye of the Tiger", "Survivor"),
    ("Remember The Name", "Fort Minor"),
    ("Not Afraid", "Eminem"),
    ("Titanium", "David Guetta"),
    ("Unstoppable", "Sia"),
    ("Believer", "Imagine Dragons"),
    ("Can't Hold Us", "Macklemore & Ryan Lewis"),
    ("Rise Up", "Andra Day"),
    ("The Climb", "Miley Cyrus"),
    ("Fight Song", "Rachel Platten"),
    ("Roar", "Katy Perry"),
    ("Skyscraper", "Demi Lovato"),
    ("Girl On Fire", "Alicia Keys"),
    ("Survivor", "Destiny's Child"),
    ("Dream On", "Aerosmith"),
    ("We Will Rock You", "Queen"),
    ("Champion", "Fall Out Boy"),
    ("Whatever It Takes", "Imagine Dragons"),
    ("Thunder", "Imagine Dragons"),
    ("My Songs Know What You Did In The Dark", "Fall Out Boy"),
    ("Power", "Kanye West"),
    ("Stronger (What Doesn't Kill You)", "Kelly Clarkson"),
    ("I Lived", "OneRepublic"),
    ("Born This Way", "Lady Gaga"),
    ("On Top Of The World", "Imagine Dragons"),
    ("Good Feeling", "Flo Rida"),
    ("Started From The Bottom", "Drake"),
    ("Till I Collapse", "Eminem"),
    ("Rise", "Katy Perry"),
    ("Brave", "Sara Bareilles"),
    ("Invincible", "Kelly Clarkson"),
    ("The Man", "Aloe Blacc"),
    ("Ain't No Stoppin' Us Now", "McFadden & Whitehead"),
    ("Run The World (Girls)", "Beyonce"),
    ("Don't Stop Believin'", "Journey"),
    ("Higher", "The Score"),
    ("Legend", "The Score"),
    ("Miracle", "The Score"),
    ("Never Give Up", "Sia"),
    ("Stronger Than Ever", "Raleigh Ritchie"),
    ("Shake It Out", "Florence + The Machine"),
    ("Glorious", "Macklemore"),
    ("Good To Be Alive (Hallelujah)", "Andy Grammer"),
    ("The Fighter", "Keith Urban"),
    ("Confident", "Demi Lovato"),
    ("This Is Me", "Keala Settle"),
    ("Rise", "Jonas Blue"),
)

SOOTHING_SEED_TRACKS = _seed_tracks(
    ("Weightless", "Marconi Union"),
    ("River Flows In You", "Yiruma"),
    ("Sunset Lover", "Petit Biscuit"),
    ("Nuvole Bianche", "Ludovico Einaudi"),
    ("Clair De Lune", "Claude Debussy"),
    ("Experience", "Ludovico Einaudi"),
    ("Holocene", "Bon Iver"),
    ("Bloom", "The Paper Kites"),
    ("Anchor", "Novo Amor"),
    ("Wait", "M83"),
    ("Your Hand In Mine", "Explosions In The Sky"),
    ("Hoppipolla", "Sigur Ros"),
    ("First Day Of My Life", "Bright Eyes"),
    ("Better Together", "Jack Johnson"),
    ("Banana Pancakes", "Jack Johnson"),
    ("Cherry Wine", "Hozier"),
    ("Sea Of Love", "Cat Power"),
    ("Mystery Of Love", "Sufjan Stevens"),
    ("Flightless Bird, American Mouth", "Iron & Wine"),
    ("The Stable Song", "Gregory Alan Isakov"),
    ("San Luis", "Gregory Alan Isakov"),
    ("To Build A Home", "The Cinematic Orchestra"),
    ("Aqueous Transmission", "Incubus"),
    ("Intro", "The xx"),
    ("Awake", "Tycho"),
    ("A Walk", "Tycho"),
    ("Days To Come", "Bonobo"),
    ("Night Owl", "Galimatias"),
    ("Open", "Rhye"),
    ("Says", "Nils Frahm"),
    ("Near Light", "Olafur Arnalds"),
    ("Only Time", "Enya"),
    ("Saturn", "Sleeping At Last"),
    ("Turning Page", "Sleeping At Last"),
    ("Slow Burn", "Kacey Musgraves"),
    ("Pink + White", "Frank Ocean"),
    ("Rivers And Roads", "The Head And The Heart"),
    ("Oats In The Water", "Ben Howard"),
    ("From Gold", "Novo Amor"),
    ("Northern Wind", "City and Colour"),
    ("Sweet Disposition", "The Temper Trap"),
    ("Work Song", "Hozier"),
    ("Orange Sky", "Alexi Murdoch"),
    ("Let It Be", "The Beatles"),
    ("Blackbird", "The Beatles"),
    ("Fix You", "Coldplay"),
    ("Come Away With Me", "Norah Jones"),
    ("Breathe", "Telepopmusik"),
    ("The Night We Met", "Lord Huron"),
    ("Landslide", "Fleetwood Mac"),
)

SURPRISING_SEED_TRACKS = _seed_tracks(
    ("Bohemian Rhapsody", "Queen"),
    ("Electric Feel", "MGMT"),
    ("Take Five", "The Dave Brubeck Quartet"),
    ("Paranoid Android", "Radiohead"),
    ("Time To Pretend", "MGMT"),
    ("Feel Good Inc.", "Gorillaz"),
    ("Paper Planes", "M.I.A."),
    ("Midnight City", "M83"),
    ("Starman", "David Bowie"),
    ("Space Oddity", "David Bowie"),
    ("Virtual Insanity", "Jamiroquai"),
    ("Dog Days Are Over", "Florence + The Machine"),
    ("Somebody That I Used To Know", "Gotye"),
    ("Little Dark Age", "MGMT"),
    ("Kids", "MGMT"),
    ("Running Up That Hill", "Kate Bush"),
    ("Go", "The Chemical Brothers"),
    ("Breezeblocks", "alt-J"),
    ("Pyramid Song", "Radiohead"),
    ("Teardrop", "Massive Attack"),
    ("1901", "Phoenix"),
    ("Safe And Sound", "Capital Cities"),
    ("Pumped Up Kicks", "Foster The People"),
    ("Once In A Lifetime", "Talking Heads"),
    ("DARE", "Gorillaz"),
    ("Around The World", "Daft Punk"),
    ("Instant Crush", "Daft Punk"),
    ("Lisztomania", "Phoenix"),
    ("Elephant", "Tame Impala"),
    ("Let It Happen", "Tame Impala"),
    ("Gooey", "Glass Animals"),
    ("Take Me Out", "Franz Ferdinand"),
    ("Reptilia", "The Strokes"),
    ("Video Killed The Radio Star", "The Buggles"),
    ("Midnight In A Perfect World", "DJ Shadow"),
    ("Wolf Like Me", "TV On The Radio"),
    ("Seven Nation Army", "The White Stripes"),
    ("Psycho Killer", "Talking Heads"),
    ("House Of Jealous Lovers", "The Rapture"),
    ("Frontier Psychiatrist", "The Avalanches"),
    ("Come With Me Now", "KONGOS"),
    ("Intro", "alt-J"),
    ("Stolen Dance", "Milky Chance"),
    ("Take A Walk", "Passion Pit"),
    ("Harness Your Hopes", "Pavement"),
    ("Temptation Waits", "Garbage"),
    ("Rabbit Heart (Raise It Up)", "Florence + The Machine"),
    ("Sleepyhead", "Passion Pit"),
    ("Cough Syrup", "Young The Giant"),
    ("This Head I Hold", "Electric Guest"),
)

ROMANTIC_SEED_TRACKS = _seed_tracks(
    ("Perfect", "Ed Sheeran"),
    ("All Of Me", "John Legend"),
    ("Thinking Out Loud", "Ed Sheeran"),
    ("At Last", "Etta James"),
    ("Make You Feel My Love", "Adele"),
    ("Can't Help Falling In Love", "Elvis Presley"),
    ("Just The Way You Are", "Bruno Mars"),
    ("Best Part", "Daniel Caesar"),
    ("Adore You", "Harry Styles"),
    ("Love On The Brain", "Rihanna"),
    ("Say You Won't Let Go", "James Arthur"),
    ("Iris", "Goo Goo Dolls"),
    ("Truly Madly Deeply", "Savage Garden"),
    ("Endless Love", "Diana Ross & Lionel Richie"),
    ("Unchained Melody", "The Righteous Brothers"),
    ("My Girl", "The Temptations"),
    ("L-O-V-E", "Nat King Cole"),
    ("Lucky", "Jason Mraz & Colbie Caillat"),
    ("A Thousand Years", "Christina Perri"),
    ("All My Life", "K-Ci & JoJo"),
    ("You Are The Best Thing", "Ray LaMontagne"),
    ("Wonderful Tonight", "Eric Clapton"),
    ("Let's Stay Together", "Al Green"),
    ("Come Away With Me", "Norah Jones"),
    ("Your Song", "Elton John"),
    ("Kiss Me", "Sixpence None The Richer"),
    ("Everlong", "Foo Fighters"),
    ("I Choose You", "Sara Bareilles"),
    ("Nothing's Gonna Stop Us Now", "Starship"),
    ("God Only Knows", "The Beach Boys"),
    ("Stand By Me", "Ben E. King"),
    ("More Than Words", "Extreme"),
    ("Just The Two Of Us", "Grover Washington Jr."),
    ("Crazy Love", "Van Morrison"),
    ("Better Together", "Jack Johnson"),
    ("Lover", "Taylor Swift"),
    ("Yellow", "Coldplay"),
    ("Speechless", "Dan + Shay"),
    ("You And Me", "Lifehouse"),
    ("XO", "Beyonce"),
    ("Can't Take My Eyes Off You", "Frankie Valli"),
    ("I Found You", "Alabama Shakes"),
    ("First Day Of My Life", "Bright Eyes"),
    ("Into My Arms", "Nick Cave & The Bad Seeds"),
    ("Heaven", "Bryan Adams"),
    ("Everything", "Michael Buble"),
    ("I Won't Give Up", "Jason Mraz"),
    ("Beyond", "Leon Bridges"),
    ("Sea Of Love", "Cat Power"),
    ("Home", "Edward Sharpe & The Magnetic Zeros"),
)

NOSTALGIC_SEED_TRACKS = _seed_tracks(
    ("Dreams", "Fleetwood Mac"),
    ("Yellow", "Coldplay"),
    ("Mr. Brightside", "The Killers"),
    ("Wonderwall", "Oasis"),
    ("Iris", "Goo Goo Dolls"),
    ("Fast Car", "Tracy Chapman"),
    ("Somewhere Only We Know", "Keane"),
    ("Use Somebody", "Kings Of Leon"),
    ("1979", "The Smashing Pumpkins"),
    ("Everybody Wants To Rule The World", "Tears For Fears"),
    ("Africa", "Toto"),
    ("Time After Time", "Cyndi Lauper"),
    ("Take On Me", "a-ha"),
    ("Never Gonna Give You Up", "Rick Astley"),
    ("Vienna", "Billy Joel"),
    ("Clocks", "Coldplay"),
    ("Fix You", "Coldplay"),
    ("Bittersweet Symphony", "The Verve"),
    ("Landslide", "Fleetwood Mac"),
    ("Don't Dream It's Over", "Crowded House"),
    ("Boys Of Summer", "Don Henley"),
    ("Slide", "Goo Goo Dolls"),
    ("Closing Time", "Semisonic"),
    ("Mr. Jones", "Counting Crows"),
    ("Drive", "Incubus"),
    ("Chasing Cars", "Snow Patrol"),
    ("Yellow Ledbetter", "Pearl Jam"),
    ("With Or Without You", "U2"),
    ("I Will Follow You Into The Dark", "Death Cab For Cutie"),
    ("Such Great Heights", "The Postal Service"),
    ("Dog Days Are Over", "Florence + The Machine"),
    ("Home", "Edward Sharpe & The Magnetic Zeros"),
    ("Electric Feel", "MGMT"),
    ("Sweet Disposition", "The Temper Trap"),
    ("The Middle", "Jimmy Eat World"),
    ("Ocean Avenue", "Yellowcard"),
    ("Best Of You", "Foo Fighters"),
    ("Champagne Supernova", "Oasis"),
    ("Don't Stop Believin'", "Journey"),
    ("September", "Earth, Wind & Fire"),
    ("Tiny Dancer", "Elton John"),
    ("Linger", "The Cranberries"),
    ("Zombie", "The Cranberries"),
    ("Ho Hey", "The Lumineers"),
    ("Little Talks", "Of Monsters and Men"),
    ("Riptide", "Vance Joy"),
    ("The Scientist", "Coldplay"),
    ("Sex and Candy", "Marcy Playground"),
    ("Dreams Tonite", "Alvvays"),
    ("Somewhere Out There", "Our Lady Peace"),
)

MUSIC_PICKER_DOC_SEED_TRACKS = _load_music_picker_doc_seed_tracks()


def _music_picker_seed_tracks(emotion, fallback_seed_tracks):
    return (
        MUSIC_PICKER_DOC_SEED_TRACKS.get(emotion)
        or _dedupe_seed_tracks(fallback_seed_tracks)
    )


HAPPY_SEED_TRACKS = _music_picker_seed_tracks('happy', HAPPY_SEED_TRACKS)
SAD_SEED_TRACKS = _music_picker_seed_tracks('sad', SAD_SEED_TRACKS)
ANGRY_SEED_TRACKS = _music_picker_seed_tracks('angry', ANGRY_SEED_TRACKS)
MOTIVATIONAL_SEED_TRACKS = _music_picker_seed_tracks(
    'motivational',
    MOTIVATIONAL_SEED_TRACKS,
)
FEAR_SEED_TRACKS = _music_picker_seed_tracks('fear', SOOTHING_SEED_TRACKS)
DEPRESSING_SEED_TRACKS = _music_picker_seed_tracks(
    'depressing',
    SAD_SEED_TRACKS[:30] + SOOTHING_SEED_TRACKS[:20],
)
SURPRISING_SEED_TRACKS = _music_picker_seed_tracks(
    'surprising',
    SURPRISING_SEED_TRACKS,
)
STRESSED_SEED_TRACKS = _music_picker_seed_tracks('stressed', SOOTHING_SEED_TRACKS)
CALM_SEED_TRACKS = _music_picker_seed_tracks('calm', SOOTHING_SEED_TRACKS)
LONELY_SEED_TRACKS = _music_picker_seed_tracks(
    'lonely',
    SAD_SEED_TRACKS[:20] + NOSTALGIC_SEED_TRACKS[:15] + SOOTHING_SEED_TRACKS[:15],
)
ROMANTIC_SEED_TRACKS = _music_picker_seed_tracks('romantic', ROMANTIC_SEED_TRACKS)
NOSTALGIC_SEED_TRACKS = _music_picker_seed_tracks('nostalgic', NOSTALGIC_SEED_TRACKS)

EMOTION_QUERY_PROFILES = {
    'happy': {
        'seed_tracks': HAPPY_SEED_TRACKS,
        'phrases': [
            'feel good pop songs',
            'happy upbeat songs',
            'joyful sunshine songs',
        ],
        'fallback': ['happy songs', 'upbeat pop'],
    },
    'sad': {
        'seed_tracks': SAD_SEED_TRACKS,
        'phrases': [
            'sad heartbreak songs',
            'emotional acoustic ballads',
            'melancholy singer songwriter songs',
        ],
        'fallback': ['sad songs', 'heartbreak ballads'],
    },
    'angry': {
        'seed_tracks': ANGRY_SEED_TRACKS,
        'phrases': [
            'angry rock songs',
            'rage workout songs',
            'intense metal songs',
        ],
        'fallback': ['angry songs', 'aggressive rock'],
    },
    'motivational': {
        'seed_tracks': MOTIVATIONAL_SEED_TRACKS,
        'phrases': [
            'motivational pump up songs',
            'victory anthem songs',
            'workout motivation songs',
        ],
        'fallback': ['motivational songs', 'champion anthems'],
    },
    'fear': {
        'seed_tracks': FEAR_SEED_TRACKS,
        'phrases': [
            'calming songs for anxiety',
            'peaceful ambient piano',
            'grounding acoustic songs',
        ],
        'fallback': ['healing calm songs', 'soothing ambient music'],
    },
    'depressing': {
        'seed_tracks': DEPRESSING_SEED_TRACKS,
        'phrases': [
            'soft comfort songs',
            'gentle healing acoustic songs',
            'sad comfort ballads',
        ],
        'fallback': ['comfort songs', 'gentle acoustic songs'],
    },
    'surprising': {
        'seed_tracks': SURPRISING_SEED_TRACKS,
        'phrases': [
            'unexpected indie songs',
            'genre bending pop songs',
            'eclectic discovery songs',
        ],
        'fallback': ['surprising songs', 'experimental pop'],
    },
    'stressed': {
        'seed_tracks': STRESSED_SEED_TRACKS,
        'phrases': [
            'stress relief songs',
            'calming focus music',
            'peaceful ambient piano',
        ],
        'fallback': ['relaxing songs', 'calm focus music'],
    },
    'calm': {
        'seed_tracks': CALM_SEED_TRACKS,
        'phrases': [
            'calm peaceful songs',
            'soft piano ambient',
            'gentle relaxing music',
        ],
        'fallback': ['calm songs', 'peaceful piano'],
    },
    'lonely': {
        'seed_tracks': LONELY_SEED_TRACKS,
        'phrases': [
            'lonely late night songs',
            'missing you acoustic songs',
            'alone indie songs',
        ],
        'fallback': ['lonely songs', 'late night indie'],
    },
    'romantic': {
        'seed_tracks': ROMANTIC_SEED_TRACKS,
        'phrases': [
            'romantic love songs',
            'slow dance songs',
            'sweet rnb love songs',
        ],
        'fallback': ['romantic songs', 'love ballads'],
    },
    'nostalgic': {
        'seed_tracks': NOSTALGIC_SEED_TRACKS,
        'phrases': [
            'nostalgic throwback songs',
            'retro memories songs',
            'classic sing along songs',
        ],
        'fallback': ['nostalgic songs', 'throwback classics'],
    },
    'mixed': {
        'seed_tracks': (
            HAPPY_SEED_TRACKS[:10]
            + SAD_SEED_TRACKS[:10]
            + MOTIVATIONAL_SEED_TRACKS[:10]
            + SURPRISING_SEED_TRACKS[:10]
            + NOSTALGIC_SEED_TRACKS[:10]
        ),
        'phrases': [
            'mixed mood songs',
            'balanced indie pop',
            'emotional variety songs',
        ],
        'fallback': ['mood mix', 'indie mix'],
    },
}

EMOTION_ALIGNMENT_HINTS = {
    'happy': {
        'boost_terms': ['happy', 'joy', 'upbeat', 'feel good', 'summer', 'sunshine'],
        'avoid_terms': ['sad', 'cry', 'sleep', 'lullaby', 'funeral'],
    },
    'sad': {
        'boost_terms': ['sad', 'heartbreak', 'melancholy', 'emotional', 'acoustic'],
        'avoid_terms': ['party', 'workout', 'rage', 'aggressive', 'hype'],
    },
    'angry': {
        'boost_terms': ['angry', 'rage', 'intense', 'powerful', 'aggressive'],
        'avoid_terms': ['sleep', 'meditation', 'lullaby', 'soft piano'],
    },
    'motivational': {
        'boost_terms': ['motivational', 'workout', 'champion', 'victory', 'power'],
        'avoid_terms': ['cry', 'hopeless', 'sleep', 'ambient'],
    },
    'fear': {
        'boost_terms': ['calm', 'steady', 'ambient', 'healing', 'peaceful'],
        'avoid_terms': ['rage', 'aggressive', 'party', 'workout'],
    },
    'depressing': {
        'boost_terms': ['gentle', 'soft', 'comfort', 'healing', 'acoustic'],
        'avoid_terms': ['party', 'workout', 'aggressive', 'rage'],
    },
    'surprising': {
        'boost_terms': ['unexpected', 'eclectic', 'experimental', 'diverse', 'fresh'],
        'avoid_terms': ['sleep', 'funeral', 'lullaby'],
    },
    'stressed': {
        'boost_terms': ['calm', 'peaceful', 'relaxing', 'meditation', 'study'],
        'avoid_terms': ['rage', 'aggressive', 'party', 'workout', 'metal'],
    },
    'calm': {
        'boost_terms': ['calm', 'peaceful', 'ambient', 'relaxing', 'meditation'],
        'avoid_terms': ['rage', 'aggressive', 'party', 'workout', 'beast mode'],
    },
    'lonely': {
        'boost_terms': ['lonely', 'alone', 'solitude', 'missing you', 'acoustic'],
        'avoid_terms': ['party', 'workout', 'aggressive', 'hype'],
    },
    'romantic': {
        'boost_terms': ['love', 'romance', 'romantic', 'sweet', 'slow jam'],
        'avoid_terms': ['rage', 'aggressive', 'workout', 'beast mode'],
    },
    'nostalgic': {
        'boost_terms': ['nostalgic', 'retro', 'throwback', 'classic', 'memory'],
        'avoid_terms': ['rage', 'aggressive', 'workout'],
    },
    'mixed': {
        'boost_terms': ['mix', 'variety', 'indie', 'alternative', 'balance'],
        'avoid_terms': [],
    },
}

EMOTION_SELECTION_REASON_WEIGHTS = {
    'music_md_playlist_seed': 3.0,
    'curated_seed': 2.2,
    'emotion_preference': 2.5,
    'emotion_keyword_match': 1.7,
    'emotion_genre_match': 1.2,
    'preferred_artist_match': 1.2,
    'artist_preference_history': 0.9,
    'favorite_track': 0.8,
    'recent_emotion_history': 0.9,
}

EMOTION_SPECIFIC_PERSONALIZATION_REASONS = {
    'emotion_preference',
    'emotion_keyword_match',
    'emotion_genre_match',
    'recent_emotion_history',
}

EMOTION_SOURCE_WEIGHTS = {
    'music_md_playlist': 3.4,
    'curated_seed': 2.4,
    'user_preference': 2.8,
    'spotify_top_tracks': 2.2,
    'spotify_saved_tracks': 1.9,
    'spotify_recently_played': 1.6,
    'favorite_track': 1.6,
    'spotify_catalog': 1.2,
    'curated_fallback': 0.8,
}

CURATED_CONTEXT_LIBRARY = {
    'happy_hits': {
        'id': '37i9dQZF1DXdPec7aLTmlC',
        'item_type': 'playlist',
        'name': 'Happy Hits!',
        'artist': 'Spotify',
        'album': 'Curated mood playlist',
    },
    'feel_good_dinner': {
        'id': '37i9dQZF1DXbm6HfkbMtFZ',
        'item_type': 'playlist',
        'name': 'Feel Good Dinner',
        'artist': 'Spotify',
        'album': 'Curated mood playlist',
    },
    'top_50_global': {
        'id': '37i9dQZEVXbMDoHDwVN2tF',
        'item_type': 'playlist',
        'name': 'Top 50 Global',
        'artist': 'Spotify',
        'album': 'Curated chart playlist',
    },
    'confidence_boost': {
        'id': '37i9dQZF1DX4fpCWaHOned',
        'item_type': 'playlist',
        'name': 'Confidence Boost',
        'artist': 'Spotify',
        'album': 'Curated motivation playlist',
    },
    'beast_mode': {
        'id': '37i9dQZF1DX9oh43oAzkyx',
        'item_type': 'playlist',
        'name': 'Beast Mode Hip-Hop',
        'artist': 'Spotify',
        'album': 'Curated motivation playlist',
    },
    'new_music_friday': {
        'id': '37i9dQZF1DX4JAvHpjipBk',
        'item_type': 'playlist',
        'name': 'New Music Friday',
        'artist': 'Spotify',
        'album': 'Curated discovery playlist',
    },
    'sad_songs': {
        'id': '37i9dQZF1DX7qK8ma5wgG1',
        'item_type': 'playlist',
        'name': 'Sad Songs',
        'artist': 'Spotify',
        'album': 'Curated comfort playlist',
    },
    'timeless_love': {
        'id': '37i9dQZF1DX7rOY2tZUw1k',
        'item_type': 'playlist',
        'name': 'Timeless Love Songs',
        'artist': 'Spotify',
        'album': 'Curated romance playlist',
    },
    'deep_focus': {
        'id': '37i9dQZF1DWZeKCadgRdKQ',
        'item_type': 'playlist',
        'name': 'Deep Focus',
        'artist': 'Spotify',
        'album': 'Curated calm playlist',
    },
    'ambient_relaxation': {
        'id': '37i9dQZF1DX3Ogo9pFvBkY',
        'item_type': 'playlist',
        'name': 'Ambient Relaxation',
        'artist': 'Spotify',
        'album': 'Curated calm playlist',
    },
    'peaceful_piano': {
        'id': '37i9dQZF1DX4sWSpwq3LiO',
        'item_type': 'playlist',
        'name': 'Peaceful Piano',
        'artist': 'Spotify',
        'album': 'Curated calm playlist',
    },
    'all_out_80s': {
        'id': '37i9dQZF1DX4UtSsGT1Sbe',
        'item_type': 'playlist',
        'name': 'All Out 80s',
        'artist': 'Spotify',
        'album': 'Curated nostalgia playlist',
    },
    'beatles_radio': {
        'id': '3WrFJ7ztbogyGnTHbHJFl2',
        'item_type': 'artist',
        'name': 'The Beatles',
        'artist': 'Spotify',
        'album': 'Curated artist radio',
    },
}

CURATED_PLAYABLE_CONTEXTS = {
    'happy': ['happy_hits', 'feel_good_dinner', 'top_50_global'],
    'sad': ['sad_songs', 'timeless_love', 'all_out_80s'],
    'angry': ['beast_mode', 'confidence_boost', 'new_music_friday'],
    'motivational': ['confidence_boost', 'beast_mode', 'happy_hits'],
    'fear': ['ambient_relaxation', 'deep_focus', 'peaceful_piano'],
    'depressing': ['sad_songs', 'ambient_relaxation', 'timeless_love'],
    'surprising': ['new_music_friday', 'top_50_global', 'happy_hits'],
    'stressed': ['deep_focus', 'ambient_relaxation', 'peaceful_piano'],
    'calm': ['peaceful_piano', 'deep_focus', 'ambient_relaxation'],
    'lonely': ['sad_songs', 'timeless_love', 'all_out_80s'],
    'romantic': ['timeless_love', 'feel_good_dinner', 'happy_hits'],
    'nostalgic': ['all_out_80s', 'beatles_radio', 'timeless_love'],
    'mixed': ['top_50_global', 'new_music_friday', 'happy_hits'],
}


