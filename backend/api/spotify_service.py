"""
Spotify API Service for EmoTune
Handles authentication, track search, and playlist generation
"""
import requests
import base64
import time
import re
from datetime import timedelta
from urllib.parse import urlencode, urlparse
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

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
        'seed_tracks': SOOTHING_SEED_TRACKS,
        'phrases': [
            'calming songs for anxiety',
            'peaceful ambient piano',
            'grounding acoustic songs',
        ],
        'fallback': ['healing calm songs', 'soothing ambient music'],
    },
    'depressing': {
        'seed_tracks': SAD_SEED_TRACKS[:30] + SOOTHING_SEED_TRACKS[:20],
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
        'seed_tracks': SOOTHING_SEED_TRACKS,
        'phrases': [
            'stress relief songs',
            'calming focus music',
            'peaceful ambient piano',
        ],
        'fallback': ['relaxing songs', 'calm focus music'],
    },
    'calm': {
        'seed_tracks': SOOTHING_SEED_TRACKS,
        'phrases': [
            'calm peaceful songs',
            'soft piano ambient',
            'gentle relaxing music',
        ],
        'fallback': ['calm songs', 'peaceful piano'],
    },
    'lonely': {
        'seed_tracks': SAD_SEED_TRACKS[:20] + NOSTALGIC_SEED_TRACKS[:15] + SOOTHING_SEED_TRACKS[:15],
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


class SpotifyAuthError(Exception):
    def __init__(self, status_code, query, response_text=''):
        self.status_code = status_code
        self.query = query
        self.response_text = response_text
        super().__init__(f"Spotify auth failed with status {status_code} for query {query!r}")


class SpotifyService:
    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.redirect_uri = settings.SPOTIFY_REDIRECT_URI
        self.request_timeout_seconds = max(
            float(getattr(settings, 'SPOTIFY_HTTP_TIMEOUT_SECONDS', 3)),
            0.5,
        )
        self.recommendation_budget_seconds = max(
            float(getattr(settings, 'SPOTIFY_RECOMMENDATION_BUDGET_SECONDS', 6)),
            1.0,
        )
        self.llm_exact_seed_enabled = bool(
            getattr(settings, 'LLM_MUSIC_PICKER_EXACT_SONG_SEED_ENABLED', True)
        )
        self.llm_exact_seed_query_limit = max(
            int(getattr(settings, 'LLM_MUSIC_PICKER_EXACT_SONG_SEED_QUERY_LIMIT', 3) or 3),
            1,
        )
        self._client_token = None
        self._client_token_expires_at = None

    def get_auth_url(self, state=None, redirect_uri=None):
        """Generate Spotify OAuth URL"""
        resolved_redirect_uri = redirect_uri or self.redirect_uri
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': resolved_redirect_uri,
            'scope': settings.SPOTIFY_SCOPE,
        }
        if state:
            params['state'] = state
        return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"

    def _normalize_scopes(self, scopes):
        if isinstance(scopes, str):
            values = scopes.split()
        elif isinstance(scopes, (list, tuple, set)):
            values = list(scopes)
        else:
            values = []

        ordered = []
        seen = set()
        for value in values:
            scope = str(value or '').strip()
            if not scope or scope in seen:
                continue
            seen.add(scope)
            ordered.append(scope)
        return ordered

    def _required_playback_scopes(self):
        configured = getattr(settings, 'SPOTIFY_REQUIRED_PLAYBACK_SCOPES', '')
        normalized = self._normalize_scopes(configured)
        if normalized:
            return normalized
        return [
            'streaming',
            'user-modify-playback-state',
            'user-read-playback-state',
            'user-read-currently-playing',
            'app-remote-control',
        ]

    def _requested_scopes(self):
        return self._normalize_scopes(getattr(settings, 'SPOTIFY_SCOPE', ''))

    def _personalization_scope_map(self):
        return {
            'top_tracks': 'user-top-read',
            'saved_tracks': 'user-library-read',
            'recently_played': 'user-read-recently-played',
        }

    def _token_payload_summary(self, payload):
        payload = payload if isinstance(payload, dict) else {}
        return {
            'scope': self._normalize_scopes(payload.get('scope')),
            'expires_in': self._safe_int(payload.get('expires_in'), 0),
            'has_access_token': bool(str(payload.get('access_token') or '').strip()),
            'has_refresh_token': bool(str(payload.get('refresh_token') or '').strip()),
            'token_type': str(payload.get('token_type') or '').strip() or None,
        }

    def _parse_response_json(self, response):
        try:
            return response.json()
        except ValueError:
            return None

    def _extract_error_details(self, payload, response_text=''):
        error_code = None
        error_message = ''

        if isinstance(payload, dict):
            error_value = payload.get('error')
            if isinstance(error_value, dict):
                error_code = error_value.get('reason') or error_value.get('status')
                error_message = str(error_value.get('message') or '').strip()
            elif error_value is not None:
                error_code = error_value
                error_message = str(error_value).strip()

            if not error_message:
                error_message = str(payload.get('error_description') or '').strip()
            if error_code is None and payload.get('error_description'):
                error_code = payload.get('error')

        if not error_message:
            error_message = str(response_text or '').strip()

        return {
            'error_code': str(error_code).strip() or None,
            'error_message': error_message[:1000] or None,
        }

    def _classify_upstream_failure(
        self,
        status_code,
        error_message='',
        response_text='',
        *,
        endpoint='',
    ):
        combined_text = ' '.join(
            [str(error_message or '').strip(), str(response_text or '').strip()]
        ).lower()

        if status_code is None:
            return {
                'reason': 'network_error',
                'retryable': True,
                'recommended_action': (
                    'Spotify could not be reached from the backend. Check internet access, '
                    'firewall settings, and Spotify API availability.'
                ),
            }

        if status_code == 400 and (
            'invalid_client' in combined_text
            or 'invalid client' in combined_text
        ):
            return {
                'reason': 'client_credentials_invalid',
                'retryable': False,
                'recommended_action': (
                    'SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET do not match the same '
                    'Spotify app. Update the backend .env with the client secret for the '
                    'current Spotify app, then restart Django.'
                ),
            }

        if status_code == 400 and (
            'invalid_grant' in combined_text
            or 'authorization code' in combined_text
            or 'redirect uri' in combined_text
            or 'redirect_uri' in combined_text
        ):
            return {
                'reason': 'invalid_grant',
                'retryable': False,
                'recommended_action': (
                    'Spotify rejected the authorization code or redirect URI. Make sure '
                    'the redirect URI in Spotify Dashboard exactly matches '
                    'http://127.0.0.1:8000/api/spotify/callback/, then start Spotify '
                    'login again.'
                ),
            }

        if status_code == 401:
            return {
                'reason': 'token_invalid',
                'retryable': False,
                'recommended_action': (
                    'Reconnect Spotify in EmoTune because the Spotify access token is '
                    'invalid or expired.'
                ),
            }

        if status_code == 403 and (
            'user may not be registered' in combined_text
            or 'user is not registered for this application' in combined_text
            or 'not registered for this application' in combined_text
        ):
            return {
                'reason': 'developer_allowlist_required',
                'retryable': False,
                'recommended_action': (
                    'Spotify blocked this account because the app is still in Development '
                    'Mode. Add the exact Spotify account to the Spotify Developer Dashboard '
                    'user allowlist, then reconnect Spotify in EmoTune.'
                ),
            }

        if status_code == 403 and 'premium' in combined_text:
            return {
                'reason': 'premium_required',
                'retryable': False,
                'recommended_action': (
                    'Spotify Premium is required for this playback flow. Log in with a '
                    'Premium Spotify account, then reconnect EmoTune.'
                ),
            }

        if status_code == 403 and (
            'scope' in combined_text or 'insufficient client scope' in combined_text
        ):
            return {
                'reason': 'insufficient_scope',
                'retryable': False,
                'recommended_action': (
                    'Reconnect Spotify in EmoTune so Spotify can grant the missing scopes.'
                ),
            }

        if status_code == 403:
            return {
                'reason': 'forbidden',
                'retryable': False,
                'recommended_action': (
                    'Spotify rejected the request. Check the connected Spotify account and '
                    'the Spotify Developer Dashboard configuration.'
                ),
            }

        if status_code == 429:
            return {
                'reason': 'rate_limited',
                'retryable': True,
                'recommended_action': (
                    'Spotify rate-limited the request. Wait a moment and try again.'
                ),
            }

        if 500 <= status_code < 600:
            return {
                'reason': 'spotify_unavailable',
                'retryable': True,
                'recommended_action': (
                    'Spotify is temporarily unavailable. Try again shortly.'
                ),
            }

        return {
            'reason': 'spotify_request_failed',
            'retryable': status_code >= 500,
            'recommended_action': (
                'Spotify rejected the request. Review the upstream status code and body for '
                'details.'
            ),
        }

    def _build_failure_response(
        self,
        *,
        status_code,
        error_message,
        response_text=None,
        response_json=None,
        error_code=None,
        endpoint='',
        source='spotify',
    ):
        classification = self._classify_upstream_failure(
            status_code,
            error_message=error_message,
            response_text=response_text,
            endpoint=endpoint,
        )
        return {
            'ok': False,
            'status_code': status_code,
            'data': None,
            'error': error_message or 'Spotify request failed.',
            'error_code': error_code,
            'reason': classification['reason'],
            'response_text': response_text,
            'response_json': response_json,
            'endpoint': endpoint,
            'source': source,
            'retryable': classification['retryable'],
            'recommended_action': classification['recommended_action'],
        }

    def _developer_allowlist_message(self):
        return (
            'Spotify blocked this account because the app is still in Development Mode. '
            'Add this exact Spotify account to the Spotify Developer Dashboard user '
            'allowlist, then reconnect Spotify in EmoTune.'
        )

    def _has_developer_allowlist_issue(self, diagnostics):
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        for key in ('account', 'devices', 'currently_playing'):
            section = diagnostics.get(key)
            if not isinstance(section, dict):
                continue
            if (
                section.get('developer_allowlist_required')
                or section.get('error_reason') == 'developer_allowlist_required'
            ):
                return True
        return False

    def _compact_failure(self, result, *, source=None, extra=None):
        result = result if isinstance(result, dict) else {}
        compact = {
            'source': source or result.get('source'),
            'status_code': result.get('status_code'),
            'reason': result.get('reason'),
            'error': result.get('error'),
            'error_code': result.get('error_code'),
            'recommended_action': result.get('recommended_action'),
        }
        if extra:
            compact.update(extra)
        return compact

    def exchange_code(self, code, redirect_uri=None):
        """Exchange auth code for tokens"""
        resolved_redirect_uri = redirect_uri or self.redirect_uri
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = requests.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': resolved_redirect_uri,
                },
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException:
            logger.exception("Spotify token exchange failed")
            classification = self._classify_upstream_failure(
                None,
                endpoint='/api/token',
            )
            return {
                'ok': False,
                'status_code': None,
                'reason': classification['reason'],
                'error': 'Spotify token exchange request failed.',
                'error_code': None,
                'response_text': None,
                'response_json': None,
                'recommended_action': classification['recommended_action'],
            }

        payload = self._parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            logger.info(
                "Spotify token exchange status=%s redirect_uri=%s payload=%s",
                response.status_code,
                resolved_redirect_uri,
                self._token_payload_summary(payload),
            )
            return payload

        details = self._extract_error_details(payload, response.text)
        classification = self._classify_upstream_failure(
            response.status_code,
            error_message=details.get('error_message') or '',
            response_text=response.text,
            endpoint='/api/token',
        )
        logger.warning(
            "Spotify token exchange failed status=%s redirect_uri=%s body=%s",
            response.status_code,
            resolved_redirect_uri,
            response.text[:1000],
        )
        return {
            'ok': False,
            'status_code': response.status_code,
            'reason': classification['reason'],
            'error': details.get('error_message') or 'Spotify token exchange failed.',
            'error_code': details.get('error_code'),
            'response_text': response.text[:1000],
            'response_json': payload,
            'recommended_action': classification['recommended_action'],
        }

    def refresh_token(self, refresh_token):
        """Refresh an access token"""
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = requests.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                },
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException:
            logger.exception("Spotify token refresh failed")
            return {}

        payload = self._parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            logger.info(
                "Spotify token refresh status=%s payload=%s",
                response.status_code,
                self._token_payload_summary(payload),
            )
            return payload

        logger.warning(
            "Spotify token refresh failed status=%s body=%s",
            response.status_code,
            response.text[:1000],
        )
        return {}

    def get_client_token_details(self):
        """Get app-level token with structured error details."""
        if not self.client_id or not self.client_secret:
            logger.warning("Spotify client credentials are not configured")
            return {
                'ok': False,
                'status_code': None,
                'data': None,
                'error': 'Spotify client credentials are not configured.',
                'error_code': None,
                'reason': 'client_credentials_missing',
                'response_text': None,
                'response_json': None,
                'endpoint': '/api/token',
                'source': 'client_credentials',
                'retryable': False,
                'recommended_action': (
                    'Configure SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET on the backend.'
                ),
            }

        if (
            self._client_token
            and self._client_token_expires_at
            and self._client_token_expires_at > timezone.now()
        ):
            return {
                'ok': True,
                'status_code': 200,
                'token': self._client_token,
                'expires_at': self._client_token_expires_at.isoformat(),
                'source': 'client_credentials_cache',
                'cached': True,
            }

        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = requests.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={'grant_type': 'client_credentials'},
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            logger.exception("Spotify client token request failed")
            return self._build_failure_response(
                status_code=None,
                error_message=str(error),
                endpoint='/api/token',
                source='client_credentials',
            )

        payload = self._parse_response_json(response)
        if response.ok and isinstance(payload, dict):
            access_token = payload.get('access_token')
            expires_in = int(payload.get('expires_in', 3600))
            if access_token:
                self._client_token = access_token
                self._client_token_expires_at = timezone.now() + timedelta(
                    seconds=max(expires_in - 60, 60)
                )
                logger.info(
                    "Spotify client credentials token acquired expires_in=%s",
                    expires_in,
                )
                return {
                    'ok': True,
                    'status_code': response.status_code,
                    'token': access_token,
                    'expires_at': self._client_token_expires_at.isoformat(),
                    'source': 'client_credentials',
                    'cached': False,
                }

        error_details = self._extract_error_details(payload, response.text)
        logger.warning(
            "Spotify client token request failed status=%s error=%s body=%s",
            response.status_code,
            error_details['error_message'],
            response.text[:1000],
        )
        return self._build_failure_response(
            status_code=response.status_code,
            error_message=(
                error_details['error_message']
                or 'Spotify client token request failed.'
            ),
            response_text=response.text[:1000],
            response_json=payload,
            error_code=error_details['error_code'],
            endpoint='/api/token',
            source='client_credentials',
        )

    def get_client_token(self):
        """Get app-level token (no user auth required)."""
        token_details = self.get_client_token_details()
        if token_details.get('ok'):
            return token_details.get('token')
        return None

    def ensure_valid_token_with_details(self, user):
        """Ensure the user's Spotify token is valid and return debug metadata."""
        details = {
            'access_token': None,
            'refresh_attempted': False,
            'refresh_succeeded': False,
            'refresh_error': None,
            'granted_scopes': self._normalize_scopes(user.spotify_granted_scopes),
        }

        if not user.is_spotify_connected:
            details['refresh_error'] = 'spotify_not_connected'
            return details

        access_token = str(user.spotify_access_token or '').strip()
        refresh_token = str(user.spotify_refresh_token or '').strip()
        now = timezone.now()
        token_expired = (
            not access_token
            or (user.spotify_token_expires and user.spotify_token_expires <= now)
        )

        if not token_expired:
            details['access_token'] = access_token
            return details

        if not refresh_token:
            logger.warning(
                "Spotify token refresh skipped for user %s because no refresh token is stored",
                user.id,
            )
            details['refresh_error'] = 'missing_refresh_token'
            return details

        details['refresh_attempted'] = True
        token_data = self.refresh_token(refresh_token)
        new_access_token = str(token_data.get('access_token') or '').strip()
        if not new_access_token:
            logger.warning(
                "Spotify token refresh failed for user %s because no access token was returned",
                user.id,
            )
            details['refresh_error'] = 'missing_access_token_in_refresh_response'
            return details

        user.spotify_access_token = new_access_token
        new_refresh_token = str(token_data.get('refresh_token') or '').strip()
        if new_refresh_token:
            user.spotify_refresh_token = new_refresh_token
        new_scopes = self._normalize_scopes(token_data.get('scope'))
        if new_scopes:
            user.spotify_granted_scopes = new_scopes
        expires_in = int(token_data.get('expires_in') or 3600)
        user.spotify_token_expires = now + timedelta(seconds=expires_in)
        update_fields = [
            'spotify_access_token',
            'spotify_refresh_token',
            'spotify_token_expires',
            'updated_at',
        ]
        if new_scopes:
            update_fields.append('spotify_granted_scopes')
        user.save(update_fields=update_fields)
        details.update({
            'access_token': new_access_token,
            'refresh_succeeded': True,
            'granted_scopes': self._normalize_scopes(user.spotify_granted_scopes),
        })
        return details

    def ensure_valid_token(self, user):
        """Ensure user's Spotify token is valid, refresh if needed."""
        return self.ensure_valid_token_with_details(user)['access_token']

    def _spotify_request(
        self,
        method,
        token,
        path,
        params=None,
        json_body=None,
        data=None,
        timeout_seconds=None,
    ):
        """Call a Spotify Web API endpoint and return a debug-friendly payload."""
        try:
            response = requests.request(
                method,
                f"{SPOTIFY_API_BASE}{path}",
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                json=json_body,
                data=data,
                timeout=timeout_seconds or self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            logger.exception("Spotify %s %s failed", method, path)
            return self._build_failure_response(
                status_code=None,
                error_message=str(error),
                endpoint=path,
            )

        payload = self._parse_response_json(response)
        response_text = response.text or ''
        logger.info(
            "Spotify %s %s status=%s body=%s",
            method,
            path,
            response.status_code,
            response_text[:1500],
        )

        if 200 <= response.status_code < 300:
            return {
                'ok': True,
                'status_code': response.status_code,
                'data': payload,
                'response_text': response_text,
                'response_json': payload,
                'error': None,
                'error_code': None,
                'reason': None,
                'endpoint': path,
                'source': 'spotify',
                'retryable': False,
                'recommended_action': None,
            }

        error_details = self._extract_error_details(payload, response_text)
        error_message = error_details['error_message'] or response_text[:300]

        logger.warning(
            "Spotify %s %s failed with status %s: %s",
            method,
            path,
            response.status_code,
            error_message,
        )
        return self._build_failure_response(
            status_code=response.status_code,
            error_message=error_message or 'Spotify request failed.',
            response_text=response_text,
            response_json=payload,
            error_code=error_details['error_code'],
            endpoint=path,
        )

    def _spotify_get(self, token, path, params=None, timeout_seconds=None):
        return self._spotify_request(
            'GET',
            token,
            path,
            params=params,
            timeout_seconds=timeout_seconds,
        )

    def _spotify_put(self, token, path, json_body=None):
        return self._spotify_request('PUT', token, path, json_body=json_body)

    def _spotify_post(self, token, path, params=None, json_body=None):
        return self._spotify_request(
            'POST',
            token,
            path,
            params=params,
            json_body=json_body,
        )

    def _choose_transfer_device(self, devices, preferred_device_id=None):
        candidates = [
            device for device in (devices or [])
            if device.get('id') and not device.get('is_restricted')
        ]
        if not candidates:
            return None

        preferred_device_id = str(preferred_device_id or '').strip()
        if preferred_device_id:
            for device in candidates:
                if str(device.get('id')) == preferred_device_id:
                    return device

        device_priority = {
            'smartphone': 0,
            'tablet': 1,
            'computer': 2,
            'speaker': 3,
            'tv': 4,
        }
        return sorted(
            candidates,
            key=lambda device: (
                device_priority.get(str(device.get('type') or '').lower(), 99),
                str(device.get('name') or '').lower(),
            ),
        )[0]

    def get_playback_debug_status(self, user):
        """Return a structured snapshot of Spotify auth and playback readiness."""
        granted_scopes = self._normalize_scopes(user.spotify_granted_scopes)
        required_scopes = self._required_playback_scopes()
        diagnostics = {
            'spotify_connected': bool(user.is_spotify_connected),
            'oauth': {
                'client_id_configured': bool(self.client_id),
                'redirect_uri': self.redirect_uri,
                'app_remote_redirect_uri': getattr(
                    settings,
                    'SPOTIFY_APP_REMOTE_REDIRECT_URI',
                    '',
                ),
                'requested_scopes': self._requested_scopes(),
                'granted_scopes': granted_scopes,
                'required_playback_scopes': required_scopes,
                'missing_required_scopes': [],
                'has_required_playback_scopes': False,
            },
            'token': {
                'has_access_token': bool(str(user.spotify_access_token or '').strip()),
                'has_refresh_token': bool(str(user.spotify_refresh_token or '').strip()),
                'expires_at': user.spotify_token_expires.isoformat()
                if user.spotify_token_expires
                else None,
                'is_expired': bool(
                    user.spotify_token_expires
                    and user.spotify_token_expires <= timezone.now()
                ),
                'is_valid': False,
                'refresh_attempted': False,
                'refresh_succeeded': False,
                'refresh_error': None,
            },
            'account': {
                'ok': False,
                'status_code': None,
                'stored_id': user.spotify_id,
                'product': None,
                'id': None,
                'email': None,
                'display_name': None,
                'country': None,
                'premium_required': True,
                'has_premium': None,
                'premium_status_known': False,
                'developer_allowlist_required': False,
                'account_mismatch': False,
                'error': None,
                'error_code': None,
                'error_reason': None,
                'raw_error': None,
                'response_text': None,
            },
            'devices': {
                'ok': False,
                'status_code': None,
                'device_count': 0,
                'has_active_device': False,
                'active_device_id': None,
                'active_device_name': None,
                'transfer_target_device_id': None,
                'transfer_target_device_name': None,
                'devices': [],
                'error': None,
                'error_code': None,
                'error_reason': None,
                'developer_allowlist_required': False,
                'raw_error': None,
                'response_text': None,
            },
            'currently_playing': {
                'ok': False,
                'status_code': None,
                'is_playing': False,
                'progress_ms': 0,
                'item_id': None,
                'item_name': None,
                'item_type': None,
                'artist_names': [],
                'artist_name': None,
                'album_name': None,
                'duration_ms': 0,
                'image_url': None,
                'device_id': None,
                'device_name': None,
                'context_type': None,
                'context_uri': None,
                'item_uri': None,
                'error': None,
                'error_code': None,
                'error_reason': None,
                'developer_allowlist_required': False,
                'raw_error': None,
                'response_text': None,
            },
            'recommended_action': None,
        }

        token_details = self.ensure_valid_token_with_details(user)
        token = token_details['access_token']
        diagnostics['token']['is_valid'] = bool(token)
        diagnostics['token']['is_expired'] = bool(
            user.spotify_token_expires
            and user.spotify_token_expires <= timezone.now()
        )
        diagnostics['token']['refresh_attempted'] = bool(token_details['refresh_attempted'])
        diagnostics['token']['refresh_succeeded'] = bool(token_details['refresh_succeeded'])
        diagnostics['token']['refresh_error'] = token_details['refresh_error']
        diagnostics['oauth']['granted_scopes'] = self._normalize_scopes(
            token_details.get('granted_scopes')
        )
        diagnostics['oauth']['missing_required_scopes'] = [
            scope for scope in required_scopes
            if scope not in diagnostics['oauth']['granted_scopes']
        ]
        diagnostics['oauth']['has_required_playback_scopes'] = not diagnostics['oauth'][
            'missing_required_scopes'
        ]

        if not user.is_spotify_connected:
            diagnostics['recommended_action'] = (
                'Connect Spotify from the EmoTune profile screen first.'
            )
            return diagnostics

        if not token:
            diagnostics['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the access token is missing or refresh failed.'
            )
            return diagnostics

        profile_result = self.get_user_profile_result(token)
        diagnostics['account']['status_code'] = profile_result.get('status_code')
        diagnostics['account']['response_text'] = profile_result.get('response_text')
        if profile_result['ok']:
            profile = profile_result.get('data') or {}
            product = str(profile.get('product') or '').strip().lower()
            live_spotify_id = profile.get('id') or user.spotify_id
            stored_spotify_id = str(user.spotify_id or '').strip() or None
            account_mismatch = bool(
                stored_spotify_id and live_spotify_id and stored_spotify_id != live_spotify_id
            )
            if account_mismatch:
                logger.warning(
                    "Spotify account mismatch for user=%s stored_id=%s live_id=%s",
                    user.id,
                    stored_spotify_id,
                    live_spotify_id,
                )
            diagnostics['account'].update({
                'ok': True,
                'product': product or None,
                'id': live_spotify_id,
                'email': profile.get('email'),
                'display_name': profile.get('display_name'),
                'country': profile.get('country'),
                'premium_status_known': bool(product),
                'has_premium': product == 'premium',
                'account_mismatch': account_mismatch,
            })
        else:
            diagnostics['account'].update({
                'error': profile_result.get('error'),
                'error_code': profile_result.get('error_code'),
                'error_reason': profile_result.get('reason'),
                'raw_error': profile_result.get('response_json'),
                'developer_allowlist_required': (
                    profile_result.get('reason') == 'developer_allowlist_required'
                ),
            })

        current_playback_result = self._spotify_get(token, '/me/player/currently-playing')
        diagnostics['currently_playing']['status_code'] = current_playback_result.get(
            'status_code'
        )
        diagnostics['currently_playing']['response_text'] = current_playback_result.get(
            'response_text'
        )
        if current_playback_result['ok']:
            current_playback = current_playback_result.get('data') or {}
            device = current_playback.get('device') or {}
            item = current_playback.get('item') or {}
            context = current_playback.get('context') or {}
            album = item.get('album') or {}
            artists = item.get('artists') or []
            artist_names = [
                str(artist.get('name') or '').strip()
                for artist in artists
                if isinstance(artist, dict) and str(artist.get('name') or '').strip()
            ]
            images = album.get('images') or []
            image_url = None
            if images and isinstance(images[0], dict):
                image_url = images[0].get('url')
            diagnostics['currently_playing'].update({
                'ok': True,
                'is_playing': bool(current_playback.get('is_playing')),
                'progress_ms': self._safe_int(current_playback.get('progress_ms'), 0),
                'item_id': item.get('id'),
                'item_name': item.get('name'),
                'item_type': item.get('type'),
                'artist_names': artist_names,
                'artist_name': ', '.join(artist_names) if artist_names else None,
                'album_name': album.get('name'),
                'duration_ms': self._safe_int(item.get('duration_ms'), 0),
                'image_url': image_url,
                'device_id': device.get('id'),
                'device_name': device.get('name'),
                'context_type': context.get('type'),
                'context_uri': context.get('uri'),
                'item_uri': item.get('uri'),
            })
        else:
            diagnostics['currently_playing'].update({
                'error': current_playback_result.get('error'),
                'error_code': current_playback_result.get('error_code'),
                'error_reason': current_playback_result.get('reason'),
                'developer_allowlist_required': (
                    current_playback_result.get('reason') == 'developer_allowlist_required'
                ),
                'raw_error': current_playback_result.get('response_json'),
            })

        devices_result = self._spotify_get(token, '/me/player/devices')
        diagnostics['devices']['status_code'] = devices_result.get('status_code')
        diagnostics['devices']['response_text'] = devices_result.get('response_text')
        if devices_result['ok']:
            devices = (devices_result.get('data') or {}).get('devices', [])
            normalized_devices = [{
                'id': device.get('id'),
                'name': device.get('name'),
                'type': device.get('type'),
                'is_active': device.get('is_active', False),
                'is_restricted': device.get('is_restricted', False),
            } for device in devices]
            active_device = next(
                (device for device in normalized_devices if device.get('is_active')),
                None,
            )
            transfer_target = self._choose_transfer_device(normalized_devices)
            diagnostics['devices'].update({
                'ok': True,
                'device_count': len(normalized_devices),
                'has_active_device': active_device is not None,
                'active_device_id': active_device.get('id') if active_device else None,
                'active_device_name': active_device.get('name') if active_device else None,
                'transfer_target_device_id': transfer_target.get('id')
                if transfer_target
                else None,
                'transfer_target_device_name': transfer_target.get('name')
                if transfer_target
                else None,
                'devices': normalized_devices,
            })
        else:
            diagnostics['devices'].update({
                'error': devices_result.get('error'),
                'error_code': devices_result.get('error_code'),
                'error_reason': devices_result.get('reason'),
                'developer_allowlist_required': (
                    devices_result.get('reason') == 'developer_allowlist_required'
                ),
                'raw_error': devices_result.get('response_json'),
            })

        if diagnostics['oauth']['missing_required_scopes']:
            diagnostics['recommended_action'] = (
                'Spotify connected, but playback permission or active device is missing. '
                'Please reconnect EmoTune so Spotify can grant: '
                f"{', '.join(diagnostics['oauth']['missing_required_scopes'])}."
            )
        elif diagnostics['account']['account_mismatch']:
            diagnostics['recommended_action'] = (
                'Spotify connected, but the stored Spotify account does not match the live '
                'Spotify profile. Reconnect Spotify in EmoTune with the correct Spotify account.'
            )
        elif self._has_developer_allowlist_issue(diagnostics):
            diagnostics['recommended_action'] = self._developer_allowlist_message()
        elif diagnostics['account']['has_premium'] is False:
            diagnostics['recommended_action'] = (
                'Spotify Premium is required for in-app Spotify playback on Android. '
                'Log in to a Premium Spotify account on this phone.'
            )
        elif diagnostics['account']['error_reason'] == 'token_invalid':
            diagnostics['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the Spotify session is no longer valid.'
            )
        elif diagnostics['account']['ok'] is False and diagnostics['account']['error_reason']:
            diagnostics['recommended_action'] = (
                diagnostics['account']['error']
                or 'Spotify account verification failed. Check the connected Spotify account '
                'and the Spotify Developer Dashboard configuration.'
            )
        elif diagnostics['devices']['ok'] and not diagnostics['devices']['has_active_device']:
            if diagnostics['devices']['transfer_target_device_id']:
                diagnostics['recommended_action'] = (
                    'Spotify connected, but no active device is selected yet. '
                    'EmoTune will try to hand off playback to '
                    f"{diagnostics['devices']['transfer_target_device_name']} when you press play."
                )
            else:
                diagnostics['recommended_action'] = (
                    'Spotify connected, but Spotify has not exposed a playable device for this '
                    'phone yet. EmoTune can control Spotify in the background only after this '
                    'phone appears as an available Spotify playback device.'
                )
        elif diagnostics['devices']['status_code'] == 403:
            diagnostics['recommended_action'] = (
                'Reconnect Spotify in EmoTune because playback-state permission was rejected by Spotify.'
            )
        else:
            diagnostics['recommended_action'] = (
                'Open the Spotify app on this phone and approve EmoTune playback access when prompted. '
                'If no prompt appears, reconnect Spotify from the EmoTune profile screen and try again.'
            )

        return diagnostics

    def prepare_playback(self, user, device_id=None):
        """Prepare Spotify playback by validating scopes and activating a device if possible."""
        diagnostics = self.get_playback_debug_status(user)
        result = {
            'ok': False,
            'blocking_issue': None,
            'already_active': diagnostics['devices']['has_active_device'],
            'transfer_attempted': False,
            'transfer_succeeded': False,
            'device_activation_pending': False,
            'transfer_status_code': None,
            'transfer_error': None,
            'selected_device_id': None,
            'selected_device_name': None,
            'recommended_action': diagnostics['recommended_action'],
            'diagnostics': diagnostics,
        }

        if not diagnostics['spotify_connected']:
            result['blocking_issue'] = 'spotify_not_connected'
            return result

        if not diagnostics['token']['is_valid']:
            result['blocking_issue'] = 'token_invalid'
            return result

        if diagnostics['oauth']['missing_required_scopes']:
            result['blocking_issue'] = 'missing_scopes'
            return result

        if self._has_developer_allowlist_issue(diagnostics):
            result['blocking_issue'] = 'developer_allowlist_required'
            result['recommended_action'] = self._developer_allowlist_message()
            return result

        if diagnostics['account']['has_premium'] is False:
            result['blocking_issue'] = 'premium_required'
            return result

        if diagnostics['devices']['has_active_device']:
            result['ok'] = True
            result['recommended_action'] = 'Spotify playback device is ready.'
            return result

        target_device = self._choose_transfer_device(
            diagnostics['devices']['devices'],
            preferred_device_id=device_id,
        )
        if not target_device:
            result['blocking_issue'] = 'no_device'
            result['recommended_action'] = (
                'Spotify connected, but Spotify has not exposed a playable device for this '
                'phone yet. EmoTune can control Spotify in the background only after this '
                'phone appears as an available Spotify playback device.'
            )
            return result

        token = self.ensure_valid_token(user)
        if not token:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the access token expired before playback could start.'
            )
            return result

        result['transfer_attempted'] = True
        result['selected_device_id'] = target_device.get('id')
        result['selected_device_name'] = target_device.get('name')
        transfer_result = self._spotify_put(
            token,
            '/me/player',
            json_body={
                'device_ids': [target_device['id']],
                'play': True,
            },
        )
        result['transfer_status_code'] = transfer_result.get('status_code')
        if not transfer_result['ok']:
            result['transfer_error'] = transfer_result.get('error')
            result['recommended_action'] = (
                'Spotify connected, but Spotify rejected the playback handoff to this phone '
                'right now. EmoTune can control playback only after Spotify exposes this phone '
                'as an available playback device.'
            )
            return result

        time.sleep(0.9)
        updated_diagnostics = self.get_playback_debug_status(user)
        result['diagnostics'] = updated_diagnostics
        result['transfer_succeeded'] = updated_diagnostics['devices']['has_active_device']
        result['ok'] = updated_diagnostics['devices']['has_active_device']
        result['recommended_action'] = (
            'Spotify playback is ready on this phone.'
            if result['ok']
            else updated_diagnostics['recommended_action']
        )
        if not result['ok']:
            updated_devices = updated_diagnostics.get('devices') or {}
            updated_device_list = updated_devices.get('devices') or []
            selected_device_still_visible = any(
                str(device.get('id') or '') == str(target_device.get('id') or '')
                for device in updated_device_list
                if isinstance(device, dict)
            )
            if selected_device_still_visible:
                result['ok'] = True
                result['transfer_succeeded'] = True
                result['device_activation_pending'] = True
                result['recommended_action'] = (
                    'Spotify saw this phone and the playback handoff was requested. '
                    'EmoTune will retry playback on this device now.'
                )
            else:
                result['blocking_issue'] = 'no_device'
        return result

    def execute_playback_command(
        self,
        user,
        action,
        uri=None,
        device_id=None,
        position_ms=None,
        shuffle_enabled=None,
        repeat_mode=None,
    ):
        """Control Spotify playback through the Web API on the user's active device."""
        normalized_action = str(action or '').strip().lower()
        result = {
            'ok': False,
            'action': normalized_action,
            'blocking_issue': None,
            'selected_device_id': None,
            'selected_device_name': None,
            'recommended_action': None,
            'spotify_error': None,
            'playback': None,
            'preparation': None,
            'position_ms': None,
            'shuffle_enabled': None,
            'repeat_mode': None,
        }

        if normalized_action not in {
            'play',
            'pause',
            'resume',
            'next',
            'previous',
            'seek',
            'shuffle',
            'repeat',
        }:
            result['blocking_issue'] = 'unsupported_action'
            result['recommended_action'] = 'Unsupported Spotify playback action.'
            return result

        diagnostics = self.get_playback_debug_status(user)
        result['recommended_action'] = diagnostics.get('recommended_action')

        if not diagnostics['spotify_connected']:
            result['blocking_issue'] = 'spotify_not_connected'
            result['recommended_action'] = (
                'Connect Spotify from the EmoTune profile screen first.'
            )
            return result

        if not diagnostics['token']['is_valid']:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the Spotify access token is not valid.'
            )
            return result

        if diagnostics['oauth']['missing_required_scopes']:
            result['blocking_issue'] = 'missing_scopes'
            result['recommended_action'] = (
                diagnostics.get('recommended_action')
                or 'Reconnect Spotify in EmoTune so Spotify can grant the required playback scopes.'
            )
            return result

        if self._has_developer_allowlist_issue(diagnostics):
            result['blocking_issue'] = 'developer_allowlist_required'
            result['recommended_action'] = self._developer_allowlist_message()
            return result

        if diagnostics['account']['has_premium'] is False:
            result['blocking_issue'] = 'premium_required'
            result['recommended_action'] = (
                'Spotify Premium is required for remote playback control on Android.'
            )
            return result

        token = self.ensure_valid_token(user)
        if not token:
            result['blocking_issue'] = 'token_invalid'
            result['recommended_action'] = (
                'Reconnect Spotify in EmoTune because the Spotify session could not be refreshed.'
            )
            return result

        preparation = None
        target_device_id = None
        target_device_name = None
        request_params = None

        if normalized_action in {
            'play',
            'resume',
            'next',
            'previous',
            'seek',
            'shuffle',
            'repeat',
        }:
            preparation = self.prepare_playback(user, device_id=device_id)
            result['preparation'] = preparation
            if not preparation.get('ok'):
                result['blocking_issue'] = preparation.get('blocking_issue') or 'no_device'
                result['recommended_action'] = (
                    preparation.get('recommended_action')
                    or diagnostics.get('recommended_action')
                )
                return result

            target_device_id = (
                str(preparation.get('selected_device_id') or '').strip()
                or str(
                    (
                        preparation.get('diagnostics') or {}
                    ).get('devices', {}).get('active_device_id') or ''
                ).strip()
            )
            target_device_name = (
                str(preparation.get('selected_device_name') or '').strip()
                or str(
                    (
                        preparation.get('diagnostics') or {}
                    ).get('devices', {}).get('active_device_name') or ''
                ).strip()
            )
            if target_device_id:
                request_params = {'device_id': target_device_id}

        result['selected_device_id'] = target_device_id or None
        result['selected_device_name'] = target_device_name or None

        command_result = None
        if normalized_action == 'play':
            normalized_uri = str(uri or '').strip()
            if not normalized_uri.startswith('spotify:'):
                result['blocking_issue'] = 'invalid_uri'
                result['recommended_action'] = (
                    'EmoTune needs a valid Spotify URI before it can start playback.'
                )
                return result

            item_parts = normalized_uri.split(':', 2)
            item_type = item_parts[1] if len(item_parts) >= 2 else 'track'
            play_body = (
                {'uris': [normalized_uri]}
                if item_type in {'track', 'episode'}
                else {'context_uri': normalized_uri}
            )
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/play',
                params=request_params,
                json_body=play_body,
            )
        elif normalized_action == 'resume':
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/play',
                params=request_params,
            )
        elif normalized_action == 'pause':
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/pause',
            )
        elif normalized_action == 'next':
            command_result = self._spotify_post(
                token,
                '/me/player/next',
                params=request_params,
            )
        elif normalized_action == 'previous':
            command_result = self._spotify_post(
                token,
                '/me/player/previous',
                params=request_params,
            )
        elif normalized_action == 'seek':
            safe_position_ms = max(self._safe_int(position_ms, 0), 0)
            result['position_ms'] = safe_position_ms
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/seek',
                params={
                    **(request_params or {}),
                    'position_ms': safe_position_ms,
                },
            )
        elif normalized_action == 'shuffle':
            normalized_shuffle = bool(shuffle_enabled)
            result['shuffle_enabled'] = normalized_shuffle
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/shuffle',
                params={
                    **(request_params or {}),
                    'state': str(normalized_shuffle).lower(),
                },
            )
        elif normalized_action == 'repeat':
            normalized_repeat_mode = str(repeat_mode or '').strip().lower()
            if normalized_repeat_mode not in {'off', 'track', 'context'}:
                result['blocking_issue'] = 'invalid_repeat_mode'
                result['recommended_action'] = (
                    'Repeat mode must be one of: off, track, context.'
                )
                return result
            result['repeat_mode'] = normalized_repeat_mode
            command_result = self._spotify_request(
                'PUT',
                token,
                '/me/player/repeat',
                params={
                    **(request_params or {}),
                    'state': normalized_repeat_mode,
                },
            )

        if (
            command_result
            and not command_result.get('ok')
            and preparation
            and preparation.get('device_activation_pending')
            and normalized_action in {'play', 'resume', 'seek', 'shuffle', 'repeat'}
        ):
            time.sleep(1.1)
            if normalized_action == 'play':
                normalized_uri = str(uri or '').strip()
                item_parts = normalized_uri.split(':', 2)
                item_type = item_parts[1] if len(item_parts) >= 2 else 'track'
                play_body = (
                    {'uris': [normalized_uri]}
                    if item_type in {'track', 'episode'}
                    else {'context_uri': normalized_uri}
                )
                command_result = self._spotify_request(
                    'PUT',
                    token,
                    '/me/player/play',
                    params=request_params,
                    json_body=play_body,
                )
            elif normalized_action == 'resume':
                command_result = self._spotify_request(
                    'PUT',
                    token,
                    '/me/player/play',
                    params=request_params,
                )
            elif normalized_action == 'seek':
                command_result = self._spotify_request(
                    'PUT',
                    token,
                    '/me/player/seek',
                    params={
                        **(request_params or {}),
                        'position_ms': result['position_ms'] or 0,
                    },
                )
            elif normalized_action == 'shuffle':
                command_result = self._spotify_request(
                    'PUT',
                    token,
                    '/me/player/shuffle',
                    params={
                        **(request_params or {}),
                        'state': str(bool(result['shuffle_enabled'])).lower(),
                    },
                )
            elif normalized_action == 'repeat':
                command_result = self._spotify_request(
                    'PUT',
                    token,
                    '/me/player/repeat',
                    params={
                        **(request_params or {}),
                        'state': result['repeat_mode'] or 'off',
                    },
                )

        if not command_result or not command_result.get('ok'):
            result['blocking_issue'] = (
                command_result.get('reason')
                if isinstance(command_result, dict)
                else 'spotify_request_failed'
            )
            result['recommended_action'] = (
                (command_result or {}).get('recommended_action')
                or diagnostics.get('recommended_action')
                or 'Spotify rejected the playback command.'
            )
            result['spotify_error'] = self._compact_failure(
                command_result or {},
                source='spotify_player',
            )
            return result

        playback_result = self._spotify_get(token, '/me/player/currently-playing')
        if playback_result.get('ok'):
            result['playback'] = playback_result.get('data')

        result['ok'] = True
        result['recommended_action'] = {
            'play': 'Spotify is playing the selected song on this device.',
            'resume': 'Spotify playback resumed on this device.',
            'pause': 'Spotify playback paused.',
            'next': 'Spotify skipped to the next track.',
            'previous': 'Spotify went back to the previous track.',
            'seek': 'Spotify playback jumped to the requested position.',
            'shuffle': 'Spotify shuffle mode updated.',
            'repeat': 'Spotify repeat mode updated.',
        }.get(normalized_action, 'Spotify playback command sent.')
        return result

    def _build_search_result(
        self,
        *,
        query,
        search_type,
        limit,
        upstream_result,
        items,
    ):
        upstream_result = upstream_result if isinstance(upstream_result, dict) else {}
        return {
            'ok': bool(upstream_result.get('ok')),
            'query': query,
            'search_type': search_type,
            'limit': limit,
            'items': items,
            'status_code': upstream_result.get('status_code'),
            'error': upstream_result.get('error'),
            'error_code': upstream_result.get('error_code'),
            'reason': upstream_result.get('reason'),
            'response_text': upstream_result.get('response_text'),
            'response_json': upstream_result.get('response_json'),
            'recommended_action': upstream_result.get('recommended_action'),
        }

    def search_tracks_detailed(
        self,
        query,
        token,
        limit=10,
        timeout_seconds=None,
    ):
        """Search for tracks and return structured upstream details."""
        limit = self._clamp_spotify_search_limit(limit, default=10)
        if not token:
            return self._build_search_result(
                query=query,
                search_type='track',
                limit=limit,
                upstream_result=self._build_failure_response(
                    status_code=None,
                    error_message='No Spotify token is available for track search.',
                    endpoint='/search',
                ),
                items=[],
            )

        upstream_result = self._spotify_get(
            token,
            '/search',
            params={'q': query, 'type': 'track', 'limit': limit},
            timeout_seconds=timeout_seconds,
        )
        items = []
        if upstream_result.get('ok'):
            tracks = (upstream_result.get('data') or {}).get('tracks', {}).get('items', [])
            items = self._format_tracks(tracks)
        return self._build_search_result(
            query=query,
            search_type='track',
            limit=limit,
            upstream_result=upstream_result,
            items=items,
        )

    def search_tracks(
        self,
        query,
        token,
        limit=10,
        timeout_seconds=None,
        raise_on_auth=False,
    ):
        """Search for tracks."""
        result = self.search_tracks_detailed(
            query,
            token,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        if not result['ok'] and raise_on_auth and result['status_code'] in (401, 403):
            raise SpotifyAuthError(
                result['status_code'],
                query,
                result.get('response_text') or result.get('error') or '',
            )
        return result['items']

    def _get_catalog_token_candidates(self, user=None):
        candidates = []
        failures = []

        client_token_details = self.get_client_token_details()
        if client_token_details.get('ok'):
            candidates.append(('client', client_token_details.get('token')))
        else:
            failures.append(self._compact_failure(client_token_details, source='client'))

        if user and getattr(user, 'is_spotify_connected', False):
            try:
                user_token_details = self.ensure_valid_token_with_details(user)
            except Exception as error:
                logger.exception("Failed to get user Spotify token for catalog requests")
                failures.append({
                    'source': 'user',
                    'status_code': None,
                    'reason': 'token_lookup_failed',
                    'error': str(error),
                    'error_code': None,
                    'recommended_action': (
                        'Reconnect Spotify in EmoTune because the stored Spotify session '
                        'could not be validated.'
                    ),
                })
            else:
                user_token = user_token_details.get('access_token')
                if user_token and all(existing != user_token for _, existing in candidates):
                    candidates.append(('user', user_token))
                elif not user_token:
                    failures.append({
                        'source': 'user',
                        'status_code': None,
                        'reason': user_token_details.get('refresh_error') or 'token_missing',
                        'error': (
                            'No usable Spotify user token is available.'
                        ),
                        'error_code': None,
                        'recommended_action': (
                            'Reconnect Spotify in EmoTune because the Spotify session could '
                            'not be refreshed.'
                        ),
                    })

        return candidates, failures

    def _get_recommendation_tokens(self, user=None):
        """Return recommendation tokens in fallback order."""
        token_candidates, _token_failures = self._get_catalog_token_candidates(user=user)
        return token_candidates

    def search_artists_detailed(
        self,
        query,
        token,
        limit=5,
        timeout_seconds=None,
    ):
        """Search for artists and return structured upstream details."""
        limit = self._clamp_spotify_search_limit(limit, default=5)
        if not token:
            return self._build_search_result(
                query=query,
                search_type='artist',
                limit=limit,
                upstream_result=self._build_failure_response(
                    status_code=None,
                    error_message='No Spotify token is available for artist search.',
                    endpoint='/search',
                ),
                items=[],
            )

        upstream_result = self._spotify_get(
            token,
            '/search',
            params={'q': query, 'type': 'artist', 'limit': limit},
            timeout_seconds=timeout_seconds,
        )
        items = []
        if upstream_result.get('ok'):
            artists = (upstream_result.get('data') or {}).get('artists', {}).get('items', [])
            items = self._format_artists(artists)
        return self._build_search_result(
            query=query,
            search_type='artist',
            limit=limit,
            upstream_result=upstream_result,
            items=items,
        )

    def search_catalog(self, query, search_type, *, user=None, limit=20):
        """Search the Spotify catalog using client credentials and user tokens as fallback."""
        search_type = str(search_type or '').strip().lower()
        limit = self._clamp_spotify_search_limit(limit, default=20)
        search_fn = (
            self.search_artists_detailed if search_type == 'artist' else self.search_tracks_detailed
        )
        token_candidates, token_failures = self._get_catalog_token_candidates(user=user)
        attempts = []
        query = str(query or '').strip()

        if not token_candidates:
            failure = token_failures[0] if token_failures else {
                'status_code': None,
                'reason': 'token_unavailable',
                'error': 'No Spotify token candidates are available for search.',
                'error_code': None,
                'recommended_action': (
                    'Check Spotify client credentials or reconnect Spotify in EmoTune.'
                ),
            }
            return {
                'ok': False,
                'query': query,
                'search_type': search_type,
                'limit': limit,
                'items': [],
                'status_code': failure.get('status_code'),
                'error': failure.get('error'),
                'error_code': failure.get('error_code'),
                'reason': failure.get('reason'),
                'response_text': None,
                'response_json': None,
                'recommended_action': failure.get('recommended_action'),
                'attempts': attempts,
                'token_failures': token_failures,
            }

        last_failure = None
        for token_source, token in token_candidates:
            result = search_fn(query, token, limit=limit)
            attempt = self._compact_failure(
                result,
                source=token_source,
                extra={'query': query, 'item_count': len(result.get('items') or [])},
            )
            attempt['ok'] = bool(result.get('ok'))
            attempts.append(attempt)
            if result.get('ok'):
                return {
                    **result,
                    'attempts': attempts,
                    'token_failures': token_failures,
                    'token_source': token_source,
                }
            last_failure = result

        last_failure = last_failure or {}
        return {
            'ok': False,
            'query': query,
            'search_type': search_type,
            'limit': limit,
            'items': [],
            'status_code': last_failure.get('status_code'),
            'error': last_failure.get('error'),
            'error_code': last_failure.get('error_code'),
            'reason': last_failure.get('reason'),
            'response_text': last_failure.get('response_text'),
            'response_json': last_failure.get('response_json'),
            'recommended_action': last_failure.get('recommended_action'),
            'attempts': attempts,
            'token_failures': token_failures,
        }

    def upstream_http_status(self, result):
        """Map Spotify dependency failures to an API HTTP status code."""
        reason = str((result or {}).get('reason') or '').strip()
        if reason in {'network_error', 'rate_limited', 'spotify_unavailable'}:
            return 503
        if reason in {'client_credentials_missing', 'client_credentials_invalid'}:
            return 500
        return 502

    def api_error_payload(self, result, *, default_message):
        """Return a consistent API-safe Spotify error payload."""
        result = result if isinstance(result, dict) else {}
        return {
            'error': default_message,
            'spotify': {
                'status_code': result.get('status_code'),
                'reason': result.get('reason'),
                'message': result.get('error'),
                'error_code': result.get('error_code'),
                'recommended_action': result.get('recommended_action'),
                'response_body': (
                    result.get('response_json')
                    if result.get('response_json') is not None
                    else result.get('response_text')
                ),
                'attempts': result.get('attempts', []),
                'token_failures': result.get('token_failures', []),
            },
        }

    def _build_recommendation_queries(
        self,
        emotion,
        preferred_artists=None,
        top_emotions=None,
        all_scores=None,
        llm_queries=None,
        playlist_category=None,
        seed_artist_name=None,
        seed_track_name=None,
        query_mode='default',
    ):
        """Build layered Spotify search queries from strongest to broadest match."""
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        normalized_query_mode = str(query_mode or 'default').strip().lower() or 'default'
        continuation_mode = normalized_query_mode == 'continuation'
        emotion_candidates = [normalized_emotion]
        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            item_emotion = str(item.get('emotion') or '').strip().lower()
            if item_emotion and item_emotion not in emotion_candidates:
                emotion_candidates.append(item_emotion)
            if len(emotion_candidates) >= 3:
                break

        if isinstance(all_scores, dict):
            scored_emotions = []
            for emotion_name, score in all_scores.items():
                normalized_name = str(emotion_name or '').strip().lower()
                if not normalized_name or normalized_name in emotion_candidates:
                    continue
                try:
                    normalized_score = float(score)
                except (TypeError, ValueError):
                    continue
                scored_emotions.append((normalized_name, normalized_score))
            scored_emotions.sort(key=lambda item: (-item[1], item[0]))
            for emotion_name, score in scored_emotions:
                if score < 0.14:
                    continue
                emotion_candidates.append(emotion_name)
                if len(emotion_candidates) >= 4:
                    break

        artists = [a.strip() for a in (preferred_artists or []) if str(a).strip()]
        playlist_category = ' '.join(str(playlist_category or '').strip().split())
        normalized_llm_queries = [
            ' '.join(str(query or '').strip().split())
            for query in (llm_queries or [])
            if ' '.join(str(query or '').strip().split())
        ]

        queries = []
        if continuation_mode:
            queries.extend(
                self._build_curated_emotion_queries(
                    normalized_emotion,
                    playlist_category=playlist_category,
                    exact_seed_limit=0,
                    phrase_limit=4,
                )
            )
            queries.extend(normalized_llm_queries)
        else:
            queries.extend(
                self._build_seed_track_queries(
                    seed_track_name=seed_track_name,
                    seed_artist_name=seed_artist_name,
                    emotion=normalized_emotion,
                    playlist_category=playlist_category,
                )
            )
            queries.extend(normalized_llm_queries)

        primary_profile = EMOTION_QUERY_PROFILES.get(
            normalized_emotion,
            EMOTION_QUERY_PROFILES['mixed'],
        )

        queries.extend(
            self._build_curated_emotion_queries(
                normalized_emotion,
                playlist_category=playlist_category,
                exact_seed_limit=1 if continuation_mode else 3,
                phrase_limit=4 if continuation_mode else 3,
            )
        )

        if playlist_category:
            queries.append(playlist_category)
            if playlist_category.lower() != normalized_emotion:
                queries.append(f'{normalized_emotion} {playlist_category}')

        for emotion_name in emotion_candidates[1:3]:
            queries.extend(
                self._build_curated_emotion_queries(
                    emotion_name,
                    playlist_category=playlist_category,
                    exact_seed_limit=0 if continuation_mode else 1,
                    phrase_limit=2 if continuation_mode else 1,
                )
            )
            if emotion_name != normalized_emotion:
                queries.append(f'{normalized_emotion} {emotion_name} songs')

        primary_phrase = (
            primary_profile.get('phrases', [normalized_emotion])[0]
            if isinstance(primary_profile, dict)
            else normalized_emotion
        )
        fallback_terms = list(
            dict.fromkeys(
                (primary_profile.get('fallback') if isinstance(primary_profile, dict) else None)
                or [f'{normalized_emotion} songs', normalized_emotion]
            )
        )

        for artist in artists[:3]:
            queries.append(f'artist:"{artist}" {primary_phrase}')
            queries.append(f'artist:"{artist}" {normalized_emotion}')
            if playlist_category:
                queries.append(f'artist:"{artist}" {playlist_category}')

        for emotion_name in emotion_candidates[:3]:
            emotion_params = EMOTION_SEARCH_PARAMS.get(
                emotion_name,
                EMOTION_SEARCH_PARAMS['mixed'],
            )
            keywords = list(
                dict.fromkeys(emotion_params.get('keywords', [])[:2] or [emotion_name])
            )
            genres = list(dict.fromkeys(emotion_params.get('genres', [])[:2]))

            for keyword, genre in zip(keywords, genres):
                queries.append(f'genre:"{genre}" {keyword}')
            for keyword in keywords:
                queries.append(keyword)
                if emotion_name != keyword:
                    queries.append(f'{emotion_name} {keyword}')

        if len(emotion_candidates) >= 2:
            blended_pair = ' '.join(emotion_candidates[:2])
            queries.append(blended_pair)
            if playlist_category:
                queries.append(f'{playlist_category} {blended_pair}')

        queries.extend(fallback_terms)
        queries.append(normalized_emotion)
        queries.append(f'{normalized_emotion} music')

        ordered_unique_queries = []
        seen = set()
        for query in queries:
            normalized = query.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_unique_queries.append(query)
        return ordered_unique_queries

    def _build_curated_emotion_queries(
        self,
        emotion,
        *,
        playlist_category='',
        exact_seed_limit=2,
        phrase_limit=2,
    ):
        profile = EMOTION_QUERY_PROFILES.get(
            str(emotion or 'mixed').strip().lower() or 'mixed',
            EMOTION_QUERY_PROFILES['mixed'],
        )
        queries = []
        seed_tracks = self._select_seed_tracks(
            profile.get('seed_tracks') or [],
            max(exact_seed_limit, 0),
        )

        for seed in seed_tracks:
            if not isinstance(seed, dict):
                continue
            queries.extend(
                self._build_exact_track_queries(
                    track_name=seed.get('track'),
                    artist_name=seed.get('artist'),
                )
            )

        for phrase in (profile.get('phrases') or [])[: max(phrase_limit, 0)]:
            normalized_phrase = ' '.join(str(phrase or '').strip().split())
            if not normalized_phrase:
                continue
            queries.append(normalized_phrase)
            if playlist_category and playlist_category.lower() not in normalized_phrase.lower():
                queries.append(f'{normalized_phrase} {playlist_category}')

        return queries

    def _select_seed_tracks(self, seed_tracks, limit):
        if limit <= 0:
            return []

        normalized_seed_tracks = [
            seed
            for seed in (seed_tracks or [])
            if isinstance(seed, dict)
        ]
        if len(normalized_seed_tracks) <= limit:
            return normalized_seed_tracks
        if limit == 1:
            return normalized_seed_tracks[:1]

        selected = []
        seen_indexes = set()
        max_index = len(normalized_seed_tracks) - 1
        for position in range(limit):
            index = round((max_index * position) / max(limit - 1, 1))
            if index in seen_indexes:
                continue
            seen_indexes.add(index)
            selected.append(normalized_seed_tracks[index])

        if len(selected) >= limit:
            return selected[:limit]

        for index, seed in enumerate(normalized_seed_tracks):
            if index in seen_indexes:
                continue
            selected.append(seed)
            if len(selected) >= limit:
                break
        return selected

    def _build_seed_track_queries(
        self,
        *,
        seed_track_name=None,
        seed_artist_name=None,
        emotion='mixed',
        playlist_category='',
    ):
        if not self.llm_exact_seed_enabled:
            return []

        queries = self._build_exact_track_queries(
            track_name=seed_track_name,
            artist_name=seed_artist_name,
        )
        if not queries:
            return []

        if playlist_category and seed_track_name:
            queries.append(
                f'"{str(seed_track_name or "").strip().replace(chr(34), "")}" {playlist_category}'
            )
        elif playlist_category and seed_artist_name:
            queries.append(
                f'artist:"{str(seed_artist_name or "").strip().replace(chr(34), "")}" {playlist_category}'
            )
        elif seed_artist_name and not seed_track_name:
            queries.append(
                f'artist:"{str(seed_artist_name or "").strip().replace(chr(34), "")}" {emotion}'
            )

        return queries[:self.llm_exact_seed_query_limit]

    def _build_exact_track_queries(
        self,
        *,
        track_name=None,
        artist_name=None,
    ):
        track_name = str(track_name or '').strip().replace('"', '')
        artist_name = str(artist_name or '').strip().replace('"', '')
        if not track_name and not artist_name:
            return []

        queries = []
        if track_name and artist_name:
            queries.extend([
                f'track:"{track_name}" artist:"{artist_name}"',
                f'"{track_name}" "{artist_name}"',
                f'artist:"{artist_name}" "{track_name}"',
            ])
        elif track_name:
            queries.extend([
                f'track:"{track_name}"',
                f'"{track_name}"',
            ])
        elif artist_name:
            queries.append(f'artist:"{artist_name}"')

        return queries

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clamp_spotify_limit(self, value, *, default=10, minimum=1, maximum=50):
        normalized = self._safe_int(value, default)
        return max(min(normalized, maximum), minimum)

    def _clamp_spotify_search_limit(self, value, *, default=5):
        return self._clamp_spotify_limit(
            value,
            default=default,
            minimum=1,
            maximum=10,
        )

    def _track_match_key(self, track):
        if not isinstance(track, dict):
            return None

        title = self._canonical_track_title(track.get('name'))
        artist = str(track.get('artist') or '').split(',', 1)[0].strip().lower()
        if not title or not artist:
            return None

        artist = re.sub(r'\s+', ' ', artist).strip()

        if not title or not artist:
            return None
        return f'{artist}|{title}'

    def _canonical_track_title(self, value):
        title = str(value or '').strip().lower()
        if not title:
            return ''
        title = re.sub(r'\s*\([^)]*\)', '', title)
        title = re.sub(
            r'\s*-\s*.*(?:live|acoustic|remix|edit|version|remaster(?:ed)?|anniversary|sped up|slowed(?: down)?|instrumental|karaoke|from ).*',
            '',
            title,
        )
        title = re.sub(r'\s+part\s+\d+\b', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def _extract_exact_query_constraints(self, query):
        normalized_query = str(query or '').strip()
        if not normalized_query:
            return None, None

        title_match = re.search(r'track:\"([^\"]+)\"', normalized_query, flags=re.IGNORECASE)
        artist_match = re.search(r'artist:\"([^\"]+)\"', normalized_query, flags=re.IGNORECASE)
        if title_match or artist_match:
            return (
                self._canonical_track_title(title_match.group(1) if title_match else ''),
                str(artist_match.group(1) if artist_match else '').strip().lower() or None,
            )

        quoted_parts = re.findall(r'"([^"]+)"', normalized_query)
        if len(quoted_parts) >= 2:
            return (
                self._canonical_track_title(quoted_parts[0]),
                str(quoted_parts[1]).strip().lower() or None,
            )
        if len(quoted_parts) == 1:
            return self._canonical_track_title(quoted_parts[0]), None
        return None, None

    def _filter_tracks_for_query(self, query, tracks):
        title_constraint, artist_constraint = self._extract_exact_query_constraints(query)
        if not title_constraint and not artist_constraint:
            return list(tracks or [])

        filtered = []
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            track_title = self._canonical_track_title(track.get('name'))
            track_artist = str(track.get('artist') or '').strip().lower()

            if title_constraint and track_title != title_constraint:
                continue
            if artist_constraint and artist_constraint not in track_artist:
                continue
            filtered.append(track)

        return filtered or list(tracks or [])

    def _normalize_playable_item(self, item, default_source='spotify'):
        if not isinstance(item, dict):
            return None

        normalized = dict(item)
        artist_name = str(normalized.get('artist') or '').strip()
        if artist_name.lower() == 'open in spotify':
            return None

        item_id = str(normalized.get('id') or '').strip()
        item_type = str(normalized.get('item_type') or '').strip() or 'track'
        uri = str(normalized.get('uri') or '').strip()
        spotify_url = str(normalized.get('spotify_url') or '').strip()

        if uri.startswith('spotify:'):
            uri_parts = uri.split(':', 2)
            if len(uri_parts) == 3:
                item_type = uri_parts[1] or item_type
                item_id = item_id or uri_parts[2]

        if spotify_url:
            parsed = urlparse(spotify_url)
            path_parts = [part for part in parsed.path.split('/') if part]
            if (
                'spotify.com' in (parsed.netloc or '')
                and len(path_parts) >= 2
                and path_parts[0] in SUPPORTED_SPOTIFY_ITEM_TYPES
            ):
                item_type = item_type or path_parts[0]
                item_id = item_id or path_parts[1]

        if (
            item_id
            and not uri
            and (not item_type or item_type in SUPPORTED_SPOTIFY_ITEM_TYPES)
        ):
            resolved_type = item_type or 'track'
            uri = f'spotify:{resolved_type}:{item_id}'
            item_type = resolved_type
        if (
            item_id
            and not spotify_url
            and (not item_type or item_type in SUPPORTED_SPOTIFY_ITEM_TYPES)
        ):
            resolved_type = item_type or 'track'
            spotify_url = f'https://open.spotify.com/{resolved_type}/{item_id}'
            item_type = resolved_type

        if not uri and not normalized.get('preview_url'):
            return None

        normalized['id'] = item_id or uri or spotify_url or normalized.get('name') or 'spotify-item'
        normalized['item_type'] = item_type
        normalized['name'] = str(normalized.get('name') or 'Spotify recommendation')
        normalized['artist'] = artist_name or 'Spotify'
        normalized['album'] = str(normalized.get('album') or '')
        normalized['image'] = str(normalized.get('image') or '')
        normalized['preview_url'] = normalized.get('preview_url')
        normalized['duration_ms'] = self._safe_int(normalized.get('duration_ms'), 0)
        normalized['uri'] = uri
        normalized['spotify_url'] = spotify_url
        normalized.setdefault('recommendation_source', default_source)
        return normalized

    def _build_saved_track_reference(
        self,
        track_id,
        name,
        artist,
        *,
        album='',
        image='',
        preview_url=None,
        duration_ms=0,
        source='saved_track',
        extra=None,
    ):
        item = self._normalize_playable_item(
            {
                'id': track_id,
                'item_type': 'track',
                'name': name,
                'artist': artist,
                'album': album,
                'image': image,
                'preview_url': preview_url,
                'duration_ms': duration_ms,
            },
            default_source=source,
        )
        if item and extra:
            item.update(extra)
        return item

    def _append_unique_tracks(self, target, seen_keys, candidates, limit):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item = self._normalize_playable_item(
                candidate,
                default_source=candidate.get('recommendation_source', 'spotify'),
            )
            if not item:
                continue
            item_key = item.get('uri') or item.get('id')
            if not item_key or item_key in seen_keys:
                continue
            seen_keys.add(item_key)
            target.append(item)
            if len(target) >= limit:
                break

    def sanitize_recommendations(self, tracks, limit=20):
        """Normalize mixed recommendation payloads into directly playable items."""
        sanitized = []
        seen_keys = set()
        seen_match_keys = set()
        for candidate in tracks or []:
            if not isinstance(candidate, dict):
                continue
            item = self._normalize_playable_item(
                candidate,
                default_source=candidate.get('recommendation_source', 'spotify'),
            )
            if not item:
                continue
            item_key = item.get('uri') or item.get('id')
            if not item_key or item_key in seen_keys:
                continue
            match_key = self._track_match_key(item)
            if match_key and match_key in seen_match_keys:
                continue
            seen_keys.add(item_key)
            if match_key:
                seen_match_keys.add(match_key)
            sanitized.append(item)
            if len(sanitized) >= limit:
                break
        return sanitized[:limit]

    def _emotion_candidate_weight_map(
        self,
        emotion,
        top_emotions=None,
        confidence_band='high',
    ):
        weights = {}
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        weights[normalized_emotion] = 1.0

        secondary_weight = {
            'high': 0.18,
            'medium': 0.28,
            'low': 0.38,
        }.get(str(confidence_band or 'high').strip().lower(), 0.25)

        for item in top_emotions or []:
            if not isinstance(item, dict):
                continue
            item_emotion = str(item.get('emotion') or '').strip().lower()
            if not item_emotion or item_emotion == normalized_emotion:
                continue
            item_confidence = max(min(float(item.get('confidence') or 0.0), 1.0), 0.0)
            weights[item_emotion] = max(
                weights.get(item_emotion, 0.0),
                round(item_confidence * secondary_weight, 4),
            )

        if str(confidence_band or '').strip().lower() == 'low':
            weights['mixed'] = max(weights.get('mixed', 0.0), 0.35)

        return weights

    def rank_tracks_for_emotion(
        self,
        tracks,
        *,
        emotion,
        top_emotions=None,
        preferred_artists=None,
        confidence_band='high',
        limit=20,
        taste_profile=None,
    ):
        sanitized = self.sanitize_recommendations(tracks or [], limit=max(limit * 2, limit))
        if not sanitized:
            return []

        preferred_artist_terms = {
            str(artist or '').strip().lower()
            for artist in (preferred_artists or [])
            if str(artist or '').strip()
        }
        normalized_taste_profile = self._normalize_taste_profile(taste_profile)
        emotion_weights = self._emotion_candidate_weight_map(
            emotion,
            top_emotions=top_emotions,
            confidence_band=confidence_band,
        )

        ranked = []
        for index, raw_track in enumerate(sanitized):
            track = dict(raw_track)
            score = 0.0
            reasons = []

            item_type = str(track.get('item_type') or 'track').strip().lower()
            if item_type == 'track':
                score += 1.0
                reasons.append('direct_track')
            else:
                score -= 4.0
                reasons.append('non_track_penalty')

            base_source = str(track.get('recommendation_source') or '').strip()
            source_weight = EMOTION_SOURCE_WEIGHTS.get(base_source, 1.0)
            if source_weight:
                score += source_weight
                if base_source:
                    reasons.append(f'source:{base_source}')

            score += float(track.get('personalization_score', 0.0) or 0.0)
            if float(track.get('personalization_score', 0.0) or 0.0) > 0:
                reasons.append('personalization_score')

            selection_reasons = [
                str(reason or '').strip()
                for reason in (track.get('selection_reasons') or [])
                if str(reason or '').strip()
            ]
            for selection_reason in selection_reasons:
                weight = EMOTION_SELECTION_REASON_WEIGHTS.get(selection_reason)
                if weight:
                    score += weight
                    reasons.append(f'reason:{selection_reason}')

            if track.get('is_preferred'):
                score += 1.6
                reasons.append('preferred_seed')

            text_blob = ' '.join([
                str(track.get('name') or '').strip().lower(),
                str(track.get('artist') or '').strip().lower(),
                str(track.get('album') or '').strip().lower(),
                base_source.lower(),
                ' '.join(selection_reasons).lower(),
            ]).strip()

            for weighted_emotion, weight in emotion_weights.items():
                profile = EMOTION_SEARCH_PARAMS.get(
                    weighted_emotion,
                    EMOTION_SEARCH_PARAMS['mixed'],
                )
                hints = EMOTION_ALIGNMENT_HINTS.get(
                    weighted_emotion,
                    EMOTION_ALIGNMENT_HINTS['mixed'],
                )
                keyword_hits = 0
                for keyword in profile.get('keywords', []):
                    keyword_text = str(keyword or '').strip().lower()
                    if keyword_text and keyword_text in text_blob:
                        keyword_hits += 1
                if keyword_hits:
                    score += min(keyword_hits, 3) * 0.8 * weight
                    reasons.append(f'keyword_fit:{weighted_emotion}')

                genre_hits = 0
                for genre in profile.get('genres', []):
                    genre_text = str(genre or '').strip().lower()
                    if genre_text and genre_text in text_blob:
                        genre_hits += 1
                if genre_hits:
                    score += min(genre_hits, 2) * 0.55 * weight
                    reasons.append(f'genre_fit:{weighted_emotion}')

                boost_hits = 0
                for term in hints.get('boost_terms', []):
                    term_text = str(term or '').strip().lower()
                    if term_text and term_text in text_blob:
                        boost_hits += 1
                if boost_hits:
                    score += min(boost_hits, 2) * 0.45 * weight
                    reasons.append(f'profile_fit:{weighted_emotion}')

                avoid_hits = 0
                for term in hints.get('avoid_terms', []):
                    term_text = str(term or '').strip().lower()
                    if term_text and term_text in text_blob:
                        avoid_hits += 1
                if avoid_hits:
                    score -= min(avoid_hits, 2) * 0.65 * weight
                    reasons.append(f'avoid_penalty:{weighted_emotion}')

            artist_text = str(track.get('artist') or '').strip().lower()
            if preferred_artist_terms and any(
                artist_term in artist_text
                for artist_term in preferred_artist_terms
            ):
                score += 1.2
                reasons.append('preferred_artist_runtime')

            discovery_bonus, discovery_reason = self._taste_discovery_bonus(
                track,
                normalized_taste_profile,
            )
            score += discovery_bonus
            if discovery_reason:
                reasons.append(discovery_reason)

            instrumental_bonus, instrumental_reason = self._taste_instrumental_bonus(
                text_blob,
                normalized_taste_profile,
            )
            score += instrumental_bonus
            if instrumental_reason:
                reasons.append(instrumental_reason)

            popularity = min(max(self._safe_int(track.get('popularity'), 0), 0), 100)
            score += popularity / 1000.0

            score -= index * 0.01

            unique_reasons = []
            seen_reasons = set()
            for reason in reasons:
                if reason in seen_reasons:
                    continue
                seen_reasons.add(reason)
                unique_reasons.append(reason)

            track['emotion_alignment_score'] = round(score, 3)
            track['emotion_alignment_reasons'] = unique_reasons
            ranked.append(track)

        ranked.sort(
            key=lambda item: (
                -float(item.get('emotion_alignment_score', 0.0)),
                -float(item.get('personalization_score', 0.0)),
                -float(item.get('popularity', 0) or 0),
                str(item.get('name') or '').lower(),
            )
        )
        return ranked[:limit]

    def blend_recommendation_groups(
        self,
        *,
        emotion,
        personalized_tracks=None,
        search_tracks=None,
        fallback_tracks=None,
        preferred_artists=None,
        limit=20,
        taste_profile=None,
    ):
        personalized_ranked = self.rank_tracks_for_emotion(
            personalized_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )
        search_ranked = self.rank_tracks_for_emotion(
            search_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )
        fallback_ranked = self.rank_tracks_for_emotion(
            fallback_tracks or [],
            emotion=emotion,
            preferred_artists=preferred_artists,
            confidence_band='medium',
            limit=max(limit * 2, limit),
            taste_profile=taste_profile,
        )

        if not personalized_ranked and not search_ranked and not fallback_ranked:
            return []

        blended = []
        seen_keys = set()

        def append_from(group, quota):
            added = 0
            for item in group:
                item_key = item.get('uri') or item.get('id')
                if not item_key or item_key in seen_keys:
                    continue
                seen_keys.add(item_key)
                blended.append(item)
                added += 1
                if added >= quota or len(blended) >= limit:
                    break

        non_mixed_emotion = str(emotion or 'mixed').strip().lower() != 'mixed'
        normalized_taste_profile = self._normalize_taste_profile(taste_profile)
        familiarity = normalized_taste_profile.get('familiarity')

        if familiarity == 'familiar':
            search_quota = min(len(search_ranked), max(1 if non_mixed_emotion else 0, limit // 3))
            fallback_quota = min(len(fallback_ranked), max(1, limit // 5)) if fallback_ranked and not search_ranked else 0
        elif familiarity == 'discovery':
            search_quota = min(len(search_ranked), max(3 if non_mixed_emotion else 2, (limit * 3) // 5))
            fallback_quota = min(len(fallback_ranked), max(2, limit // 4)) if fallback_ranked and not search_ranked else 0
        else:
            if search_ranked:
                search_quota = min(
                    len(search_ranked),
                    max(2 if non_mixed_emotion else 1, limit // 2),
                )
            else:
                search_quota = 0
            fallback_quota = 0
            if fallback_ranked and not search_ranked:
                fallback_quota = min(
                    len(fallback_ranked),
                    max(2 if non_mixed_emotion else 1, limit // 2),
                )

        personalized_quota = min(
            len(personalized_ranked),
            max(limit - search_quota - fallback_quota, 0),
        )

        if search_quota:
            append_from(search_ranked, search_quota)
        elif fallback_quota:
            append_from(fallback_ranked, fallback_quota)

        if personalized_quota:
            append_from(personalized_ranked, personalized_quota)

        if len(blended) < limit:
            append_from(search_ranked, limit)
        if len(blended) < limit:
            append_from(fallback_ranked, limit)
        if len(blended) < limit:
            append_from(personalized_ranked, limit)

        return blended[:limit]

    def select_primary_track(self, tracks):
        """Pick the single best directly playable track candidate."""
        sanitized = self.sanitize_recommendations(tracks or [], limit=max(len(tracks or []), 1))
        if not sanitized:
            return None

        track_candidates = [
            track for track in sanitized
            if str(track.get('item_type') or '').strip().lower() == 'track'
        ]
        ranked_candidates = track_candidates or sanitized
        return dict(ranked_candidates[0]) if ranked_candidates else None

    def _build_user_fallback_tracks(self, emotion, user=None, limit=20):
        if not user:
            return []

        from users.models import FavoriteTrack, PromptHistory, UserPreference

        tracks = []
        seen_keys = set()

        preferences = UserPreference.objects.filter(
            user=user,
            emotion=emotion,
        ).order_by('-play_count', '-last_played')[:limit]
        for pref in preferences:
            self._append_unique_tracks(
                tracks,
                seen_keys,
                [
                    self._build_saved_track_reference(
                        pref.spotify_track_id,
                        pref.track_name,
                        pref.artist_name,
                        source='user_preference',
                        extra={'is_preferred': True},
                    )
                ],
                limit,
            )
            if len(tracks) >= limit:
                return tracks

        histories = PromptHistory.objects.filter(
            user=user,
            detected_emotion=emotion,
        ).order_by('-created_at')[:5]
        for history in histories:
            if not self._history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            self._append_unique_tracks(tracks, seen_keys, playlist_data, limit)
            if len(tracks) >= limit:
                return tracks

        favorites = FavoriteTrack.objects.filter(user=user).order_by('-added_at')[:limit]
        for favorite in favorites:
            self._append_unique_tracks(
                tracks,
                seen_keys,
                [
                    self._build_saved_track_reference(
                        favorite.spotify_track_id,
                        favorite.track_name,
                        favorite.artist_name,
                        album=favorite.album_name,
                        image=favorite.album_image,
                        preview_url=favorite.preview_url,
                        duration_ms=favorite.duration_ms,
                        source='favorite_track',
                    )
                ],
                limit,
            )
            if len(tracks) >= limit:
                return tracks

        return tracks

    def _build_curated_fallback_tracks(self, emotion, limit=20):
        context_keys = CURATED_PLAYABLE_CONTEXTS.get(emotion, [])
        if emotion != 'mixed':
            context_keys = [*context_keys, *CURATED_PLAYABLE_CONTEXTS['mixed']]

        tracks = []
        seen_keys = set()
        for context_key in context_keys:
            context = CURATED_CONTEXT_LIBRARY.get(context_key)
            if not context:
                continue
            self._append_unique_tracks(
                tracks,
                seen_keys,
                [{**context, 'recommendation_source': 'curated_fallback'}],
                limit,
            )
            if len(tracks) >= limit:
                break
        return tracks

    def _build_fallback_tracks(self, emotion, user=None, preferred_artists=None, limit=20):
        """Return directly playable fallbacks when Spotify search fails."""
        tracks = []
        seen_keys = set()

        self._append_unique_tracks(
            tracks,
            seen_keys,
            self._build_user_fallback_tracks(emotion, user=user, limit=limit),
            limit,
        )

        if len(tracks) < limit:
            self._append_unique_tracks(
                tracks,
                seen_keys,
                self._build_curated_fallback_tracks(emotion, limit=limit),
                limit,
            )

        return tracks[:limit]

    def get_recommendations_with_details(
        self,
        emotion,
        user=None,
        preferred_artists=None,
        top_emotions=None,
        all_scores=None,
        llm_queries=None,
        playlist_category=None,
        seed_artist_name=None,
        seed_track_name=None,
        limit=20,
        include_personalization=True,
        time_budget_seconds=None,
        query_mode='default',
        taste_profile=None,
    ):
        """Get track recommendations with explicit fallback metadata."""
        result = {
            'ok': False,
            'tracks': [],
            'source': 'spotify',
            'used_fallback': False,
            'fallback_reason': None,
            'queries_tried': [],
            'token_sources_tried': [],
            'spotify_errors': [],
            'token_failures': [],
            'personalized': False,
            'personalization_sources': [],
            'personalization_missing_scopes': [],
            'personalization_errors': [],
        }

        all_tracks = []
        search_tracks = []
        seen_track_ids = set()
        seen_track_match_keys = set()
        desired_candidate_total = limit

        personalized_tracks = []
        if include_personalization:
            user_music_result = self.get_user_music_candidates(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
            )
            result['personalization_sources'] = user_music_result.get('sources_used') or []
            result['personalization_missing_scopes'] = (
                user_music_result.get('missing_scopes') or []
            )
            result['personalization_errors'] = user_music_result.get('errors') or []
            personalized_tracks = user_music_result.get('tracks') or []
            if personalized_tracks:
                result['personalized'] = True
                result['source'] = 'user_music'
                all_tracks.extend(personalized_tracks)
                seen_track_ids.update(
                    track.get('id')
                    for track in personalized_tracks
                    if track.get('id')
                )
                seen_track_match_keys.update(
                    match_key
                    for match_key in (
                        self._track_match_key(track)
                        for track in personalized_tracks
                    )
                    if match_key
                )
                desired_candidate_total = min(max(limit + 6, limit), limit * 2)

        token_candidates, token_failures = self._get_catalog_token_candidates(user=user)
        result['token_failures'] = token_failures
        if not token_candidates:
            logger.warning(
                "No Spotify API tokens available for emotion %r. Returning playable fallbacks.",
                emotion,
            )
            fallback_tracks = self._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
            )
            merged_tracks = self.blend_recommendation_groups(
                emotion=emotion,
                personalized_tracks=all_tracks,
                fallback_tracks=fallback_tracks,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
            )
            result.update({
                'ok': bool(merged_tracks),
                'tracks': merged_tracks,
                'source': 'user_music_fallback' if result['personalized'] else 'fallback',
                'used_fallback': len(merged_tracks) > len(all_tracks),
                'fallback_reason': (
                    token_failures[0]['reason'] if token_failures else 'token_unavailable'
                ),
            })
            return result

        resolved_time_budget_seconds = max(
            float(time_budget_seconds or self.recommendation_budget_seconds),
            0.5,
        )
        deadline = time.monotonic() + resolved_time_budget_seconds
        queries = self._build_recommendation_queries(
            emotion,
            preferred_artists=preferred_artists,
            top_emotions=top_emotions,
            all_scores=all_scores,
            llm_queries=llm_queries,
            playlist_category=playlist_category,
            seed_artist_name=seed_artist_name,
            seed_track_name=seed_track_name,
            query_mode=query_mode,
        )
        token_index = 0

        try:
            for query in queries:
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    logger.info(
                        "Stopping Spotify recommendation lookup for %r due to time budget",
                        emotion,
                    )
                    break

                remaining = max(desired_candidate_total - len(all_tracks), 0)
                if remaining == 0:
                    break

                while token_index < len(token_candidates):
                    token_source, token = token_candidates[token_index]
                    if token_source not in result['token_sources_tried']:
                        result['token_sources_tried'].append(token_source)
                    try:
                        search_limit = self._clamp_spotify_search_limit(
                            max(remaining, 5),
                            default=5,
                        )
                        search_result = self.search_tracks_detailed(
                            query,
                            token,
                            limit=search_limit,
                            timeout_seconds=min(self.request_timeout_seconds, remaining_time),
                        )
                        if search_result['ok']:
                            tracks = self._filter_tracks_for_query(
                                query,
                                search_result['items'],
                            )
                            break
                        if search_result['status_code'] in (401, 403):
                            raise SpotifyAuthError(
                                search_result['status_code'],
                                query,
                                search_result.get('response_text') or search_result.get('error') or '',
                            )
                        result['spotify_errors'].append(self._compact_failure(
                            search_result,
                            source=token_source,
                            extra={'query': query},
                        ))
                        tracks = []
                        break
                    except SpotifyAuthError as error:
                        logger.warning(
                            "Spotify track search using %s token failed with status %s for query %r. "
                            "Trying fallback token if available.",
                            token_source,
                            error.status_code,
                            query,
                        )
                        result['spotify_errors'].append({
                            'source': token_source,
                            'status_code': error.status_code,
                            'reason': 'spotify_auth_failed',
                            'error': error.response_text[:300] or 'Spotify rejected the token.',
                            'error_code': None,
                            'query': query,
                        })
                        token_index += 1
                else:
                    logger.warning(
                        "All available Spotify tokens were rejected while searching for emotion %r",
                        emotion,
                    )
                    break

                result['queries_tried'].append(query)

                for track in tracks:
                    track_id = track.get('id')
                    track_match_key = self._track_match_key(track)
                    if (
                        not track_id
                        or track_id in seen_track_ids
                        or (track_match_key and track_match_key in seen_track_match_keys)
                    ):
                        continue
                    seen_track_ids.add(track_id)
                    if track_match_key:
                        seen_track_match_keys.add(track_match_key)
                    search_tracks.append(track)
                    all_tracks.append(track)
                    if len(all_tracks) >= desired_candidate_total:
                        break
        except Exception:
            logger.exception("Spotify recommendation generation failed for emotion %r", emotion)
            fallback_tracks = self._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
            )
            merged_tracks = self.blend_recommendation_groups(
                emotion=emotion,
                personalized_tracks=personalized_tracks,
                search_tracks=search_tracks,
                fallback_tracks=fallback_tracks,
                preferred_artists=preferred_artists,
                limit=limit,
                taste_profile=taste_profile,
            )
            result.update({
                'ok': bool(merged_tracks),
                'tracks': merged_tracks,
                'source': 'user_music_fallback' if result['personalized'] else 'fallback',
                'used_fallback': len(merged_tracks) > len(all_tracks),
                'fallback_reason': 'exception',
            })
            return result

        if not all_tracks:
            logger.warning(
                "No Spotify recommendations found for emotion %r. Returning playable fallbacks.",
                emotion,
            )
            fallback_tracks = self._build_fallback_tracks(
                emotion,
                user=user,
                preferred_artists=preferred_artists,
                limit=limit,
            )
            result.update({
                'ok': bool(fallback_tracks),
                'tracks': fallback_tracks,
                'source': 'fallback',
                'used_fallback': True,
                'fallback_reason': (
                    result['spotify_errors'][0]['reason']
                    if result['spotify_errors']
                    else 'no_results'
                ),
            })
            return result

        search_contributed_tracks = bool(search_tracks)
        ranked_tracks = self.blend_recommendation_groups(
            emotion=emotion,
            personalized_tracks=personalized_tracks,
            search_tracks=search_tracks,
            preferred_artists=preferred_artists,
            limit=limit,
            taste_profile=taste_profile,
        )
        result.update({
            'ok': True,
            'tracks': ranked_tracks or all_tracks[:limit],
            'source': (
                'hybrid_user_music_spotify'
                if result['personalized'] and search_contributed_tracks
                else 'user_music'
                if result['personalized']
                else 'spotify'
            ),
        })
        return result

    def get_recommendations(self, emotion, user=None, preferred_artists=None, limit=20):
        """Get track recommendations based on emotion."""
        return self.get_recommendations_with_details(
            emotion,
            user=user,
            preferred_artists=preferred_artists,
            limit=limit,
        )['tracks']

    def get_user_profile_result(self, token):
        """Get Spotify user profile with structured upstream details."""
        return self._spotify_get(token, '/me')

    def get_user_profile(self, token):
        """Get Spotify user profile."""
        profile_result = self.get_user_profile_result(token)
        if profile_result.get('ok'):
            return profile_result.get('data')
        return None

    def search_artists(self, query, token, limit=5):
        """Search for artists."""
        return self.search_artists_detailed(query, token, limit=limit)['items']

    def _format_artists(self, artists):
        formatted = []
        for artist in artists:
            if not artist:
                continue
            formatted.append({
                'id': artist.get('id'),
                'name': artist.get('name'),
                'image': artist.get('images', [{}])[0].get('url') if artist.get('images') else None,
                'genres': artist.get('genres', []),
                'popularity': artist.get('popularity', 0),
            })
        return formatted

    def _format_tracks(self, tracks):
        """Format Spotify tracks into standardized format"""
        formatted = []
        for track in tracks:
            if not track:
                continue
            album = track.get('album', {})
            artists = track.get('artists', [])
            formatted.append({
                'id': track['id'],
                'name': track['name'],
                'artist': ', '.join([a['name'] for a in artists]),
                'album': album.get('name', ''),
                'image': album.get('images', [{}])[0].get('url', '') if album.get('images') else '',
                'preview_url': track.get('preview_url'),
                'duration_ms': track.get('duration_ms', 0),
                'spotify_url': track.get('external_urls', {}).get('spotify', ''),
                'uri': track.get('uri', ''),
                'popularity': self._safe_int(track.get('popularity'), 0),
            })
        return formatted

    def _format_nested_track_items(
        self,
        items,
        *,
        recommendation_source,
        played_at_key=None,
        added_at_key=None,
    ):
        formatted = []
        for item in items or []:
            track = item.get('track') if isinstance(item, dict) else None
            if not isinstance(track, dict):
                continue
            normalized_tracks = self._format_tracks([track])
            if not normalized_tracks:
                continue
            normalized = normalized_tracks[0]
            normalized['recommendation_source'] = recommendation_source
            normalized['catalog_source'] = recommendation_source
            if played_at_key and item.get(played_at_key):
                normalized['spotify_played_at'] = item.get(played_at_key)
            if added_at_key and item.get(added_at_key):
                normalized['spotify_added_at'] = item.get(added_at_key)
            formatted.append(normalized)
        return formatted

    def _build_personalization_context(self, emotion, user=None, preferred_artists=None):
        context_config = EMOTION_SEARCH_PARAMS.get(emotion, EMOTION_SEARCH_PARAMS['mixed'])
        context = {
            'emotion': str(emotion or 'mixed').strip().lower() or 'mixed',
            'keywords': [
                str(keyword or '').strip().lower()
                for keyword in context_config.get('keywords', [])
                if str(keyword or '').strip()
            ],
            'genres': [
                str(genre or '').strip().lower()
                for genre in context_config.get('genres', [])
                if str(genre or '').strip()
            ],
            'preferred_artists': {
                str(artist or '').strip().lower()
                for artist in (preferred_artists or [])
                if str(artist or '').strip()
            },
            'preferred_track_scores': {},
            'preferred_artist_scores': {},
            'favorite_track_ids': set(),
            'history_track_ids': set(),
            'recent_recommended_track_counts': {},
            'cross_emotion_recent_track_counts': {},
        }

        if not user:
            return context

        from users.models import FavoriteTrack, PromptHistory, UserPreference

        preferences = UserPreference.objects.filter(
            user=user,
            emotion=emotion,
        ).only('spotify_track_id', 'artist_name', 'play_count')
        for pref in preferences:
            track_id = str(pref.spotify_track_id or '').strip()
            artist_name = str(pref.artist_name or '').strip().lower()
            play_count = max(self._safe_int(pref.play_count, 0), 0)
            if track_id:
                context['preferred_track_scores'][track_id] = max(
                    context['preferred_track_scores'].get(track_id, 0),
                    play_count,
                )
            if artist_name:
                context['preferred_artist_scores'][artist_name] = max(
                    context['preferred_artist_scores'].get(artist_name, 0),
                    play_count,
                )

        context['favorite_track_ids'] = {
            str(track_id).strip()
            for track_id in FavoriteTrack.objects.filter(user=user)
            .values_list('spotify_track_id', flat=True)
            if str(track_id).strip()
        }

        histories = PromptHistory.objects.filter(
            user=user,
            detected_emotion=emotion,
        ).only('playlist_data')[:10]
        for history in histories:
            if not self._history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            for item in playlist_data:
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get('id') or '').strip()
                uri = str(item.get('uri') or '').strip()
                if not track_id and uri.startswith('spotify:track:'):
                    track_id = uri.split(':', 2)[-1]
                if track_id:
                    context['history_track_ids'].add(track_id)

        recent_histories = PromptHistory.objects.filter(
            user=user,
        ).only('detected_emotion', 'playlist_data')[:15]
        for history in recent_histories:
            if not self._history_allows_learning(history):
                continue
            playlist_data = history.playlist_data if isinstance(history.playlist_data, list) else []
            history_track_ids = set()
            for item in playlist_data:
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get('id') or '').strip()
                uri = str(item.get('uri') or '').strip()
                if not track_id and uri.startswith('spotify:track:'):
                    track_id = uri.split(':', 2)[-1]
                if track_id:
                    history_track_ids.add(track_id)
            for track_id in history_track_ids:
                context['recent_recommended_track_counts'][track_id] = (
                    context['recent_recommended_track_counts'].get(track_id, 0) + 1
                )
                if history.detected_emotion != emotion:
                    context['cross_emotion_recent_track_counts'][track_id] = (
                        context['cross_emotion_recent_track_counts'].get(track_id, 0) + 1
                    )

        return context

    def _score_personalized_track(self, track, context):
        track = track if isinstance(track, dict) else {}
        context = context if isinstance(context, dict) else {}
        requested_emotion = str(context.get('emotion') or 'mixed').strip().lower() or 'mixed'

        source_bonus = {
            'spotify_top_tracks': 1.6,
            'spotify_saved_tracks': 1.4,
            'spotify_recently_played': 1.1,
        }
        score = source_bonus.get(
            str(track.get('recommendation_source') or '').strip(),
            0.9,
        )

        selection_reasons = [
            str(track.get('recommendation_source') or 'spotify_catalog')
        ]
        track_id = str(track.get('id') or '').strip()
        artist_text = str(track.get('artist') or '').strip().lower()
        match_text = ' '.join([
            str(track.get('name') or '').strip().lower(),
            artist_text,
            str(track.get('album') or '').strip().lower(),
        ])
        has_emotion_signal = False

        preference_play_count = context.get('preferred_track_scores', {}).get(track_id, 0)
        if preference_play_count:
            score += 1.5 + min(preference_play_count, 8) * 0.12
            selection_reasons.append('emotion_preference')
            has_emotion_signal = True

        artist_preference_score = 0
        for preferred_artist, play_count in context.get('preferred_artist_scores', {}).items():
            if preferred_artist and preferred_artist in artist_text:
                artist_preference_score = max(artist_preference_score, play_count)
        if artist_preference_score:
            score += 0.8 + min(artist_preference_score, 8) * 0.08
            selection_reasons.append('artist_preference_history')

        preferred_artist_match = False
        for preferred_artist in context.get('preferred_artists', set()):
            if preferred_artist and preferred_artist in artist_text:
                preferred_artist_match = True
                score += 1.1
        if preferred_artist_match:
            selection_reasons.append('preferred_artist_match')

        if track_id and track_id in context.get('favorite_track_ids', set()):
            score += 0.7
            selection_reasons.append('favorite_track')

        if track_id and track_id in context.get('history_track_ids', set()):
            score += 0.35
            selection_reasons.append('recent_emotion_history')
            has_emotion_signal = True

        recent_recommended_count = context.get('recent_recommended_track_counts', {}).get(track_id, 0)
        if recent_recommended_count:
            score -= min(recent_recommended_count, 4) * 0.45
            selection_reasons.append('repeat_penalty')

        cross_emotion_repeat_count = context.get(
            'cross_emotion_recent_track_counts',
            {},
        ).get(track_id, 0)
        if cross_emotion_repeat_count:
            score -= min(cross_emotion_repeat_count, 4) * 0.9
            selection_reasons.append('cross_emotion_repeat_penalty')

        keyword_hits = 0
        for keyword in context.get('keywords', []):
            if keyword and keyword in match_text:
                keyword_hits += 1
        if keyword_hits:
            score += min(keyword_hits, 3) * 0.65
            selection_reasons.append('emotion_keyword_match')
            has_emotion_signal = True

        genre_hits = 0
        for genre in context.get('genres', []):
            if genre and genre in match_text:
                genre_hits += 1
        if genre_hits:
            score += min(genre_hits, 2) * 0.3
            selection_reasons.append('emotion_genre_match')
            has_emotion_signal = True

        if requested_emotion != 'mixed' and not has_emotion_signal:
            # Generic top/saved tracks should not dominate a clearly different mood.
            score -= 1.35
            selection_reasons.append('generic_personalization_penalty')

        score += min(max(self._safe_int(track.get('popularity'), 0), 0), 100) / 1000

        unique_reasons = []
        seen_reasons = set()
        for reason in selection_reasons:
            if reason in seen_reasons:
                continue
            seen_reasons.add(reason)
            unique_reasons.append(reason)

        enriched = dict(track)
        enriched['personalization_score'] = round(score, 3)
        enriched['selection_reasons'] = unique_reasons
        return enriched

    def _track_has_personalized_emotion_signal(self, track, emotion):
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        if normalized_emotion == 'mixed':
            return True

        selection_reasons = {
            str(reason or '').strip()
            for reason in (track.get('selection_reasons') or [])
            if str(reason or '').strip()
        }
        return bool(selection_reasons.intersection(
            EMOTION_SPECIFIC_PERSONALIZATION_REASONS
        ))

    def _history_allows_learning(self, history):
        if history is None:
            return True
        music_picker_data = (
            history.music_picker_data
            if isinstance(history.music_picker_data, dict)
            else {}
        )
        personalization = music_picker_data.get('personalization')
        return not (
            isinstance(personalization, dict)
            and personalization.get('train_session') is False
        )

    def _normalize_taste_profile(self, taste_profile):
        working = taste_profile if isinstance(taste_profile, dict) else {}
        familiarity = str(working.get('familiarity') or 'balanced').strip().lower()
        if familiarity not in {'balanced', 'familiar', 'discovery'}:
            familiarity = 'balanced'
        return {
            'familiarity': familiarity,
            'prefer_instrumental': bool(working.get('prefer_instrumental', False)),
        }

    def _taste_discovery_bonus(self, track, taste_profile):
        familiarity = taste_profile.get('familiarity')
        source = str(track.get('recommendation_source') or '').strip().lower()
        if familiarity == 'discovery':
            if source in {'spotify_catalog', 'curated_fallback'}:
                return 0.14, 'taste:discovery'
            if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference', 'favorite_track'}:
                return -0.08, 'taste:discovery'
        if familiarity == 'familiar':
            if source in {'spotify_top_tracks', 'spotify_saved_tracks', 'user_preference', 'favorite_track'}:
                return 0.12, 'taste:familiar'
            if source in {'spotify_catalog', 'curated_fallback'}:
                return -0.06, 'taste:familiar'
        return 0.0, None

    def _taste_instrumental_bonus(self, text_blob, taste_profile):
        if not taste_profile.get('prefer_instrumental'):
            return 0.0, None

        normalized_blob = str(text_blob or '').strip().lower()
        instrumental_terms = (
            'instrumental',
            'ambient',
            'piano',
            'study',
            'focus',
            'meditation',
            'sleep',
            'classical',
            'soundtrack',
            'lofi',
            'lo-fi',
        )
        vocal_terms = (
            'feat.',
            'featuring',
            'karaoke',
            'live',
            'remix',
        )

        bonus = 0.0
        if any(term in normalized_blob for term in instrumental_terms):
            bonus += 0.18
        if any(term in normalized_blob for term in vocal_terms):
            bonus -= 0.07
        if bonus > 0:
            return bonus, 'taste:instrumental'
        if bonus < 0:
            return bonus, 'taste:less_instrumental_fit'
        return 0.0, None

    def get_user_music_candidates(
        self,
        emotion,
        user=None,
        preferred_artists=None,
        limit=20,
    ):
        result = {
            'ok': False,
            'tracks': [],
            'sources_used': [],
            'missing_scopes': [],
            'errors': [],
            'token_error': None,
        }

        if not user or not getattr(user, 'is_spotify_connected', False):
            return result

        token_details = self.ensure_valid_token_with_details(user)
        token = token_details.get('access_token')
        if not token:
            result['token_error'] = token_details.get('refresh_error') or 'token_missing'
            return result

        granted_scopes = set(self._normalize_scopes(token_details.get('granted_scopes')))
        source_configs = [
            (
                'top_tracks',
                'spotify_top_tracks',
                '/me/top/tracks',
                {'time_range': 'medium_term', 'limit': min(max(limit, 10), 25)},
            ),
            (
                'saved_tracks',
                'spotify_saved_tracks',
                '/me/tracks',
                {'limit': min(max(limit, 10), 25)},
            ),
            (
                'recently_played',
                'spotify_recently_played',
                '/me/player/recently-played',
                {'limit': min(max(limit, 10), 20)},
            ),
        ]

        candidates = []
        seen_keys = set()
        personalization_context = self._build_personalization_context(
            emotion,
            user=user,
            preferred_artists=preferred_artists,
        )

        for source_key, recommendation_source, endpoint, params in source_configs:
            required_scope = self._personalization_scope_map().get(source_key)
            if required_scope and required_scope not in granted_scopes:
                result['missing_scopes'].append(required_scope)
                continue

            upstream_result = self._spotify_get(token, endpoint, params=params)
            if not upstream_result.get('ok'):
                result['errors'].append(
                    self._compact_failure(
                        upstream_result,
                        source=source_key,
                        extra={'endpoint': endpoint},
                    )
                )
                continue

            payload = upstream_result.get('data') or {}
            if source_key == 'top_tracks':
                tracks = self._format_tracks(payload.get('items', []))
                for track in tracks:
                    track['recommendation_source'] = recommendation_source
                    track['catalog_source'] = recommendation_source
            elif source_key == 'saved_tracks':
                tracks = self._format_nested_track_items(
                    payload.get('items', []),
                    recommendation_source=recommendation_source,
                    added_at_key='added_at',
                )
            else:
                tracks = self._format_nested_track_items(
                    payload.get('items', []),
                    recommendation_source=recommendation_source,
                    played_at_key='played_at',
                )

            scored_tracks = [
                self._score_personalized_track(track, personalization_context)
                for track in tracks
            ]
            self._append_unique_tracks(
                candidates,
                seen_keys,
                scored_tracks,
                limit=max(limit * 2, limit),
            )
            if scored_tracks:
                result['sources_used'].append(source_key)

        candidates.sort(
            key=lambda item: (
                -float(item.get('personalization_score', 0.0)),
                str(item.get('name') or '').lower(),
            )
        )
        normalized_emotion = str(emotion or 'mixed').strip().lower() or 'mixed'
        if normalized_emotion != 'mixed':
            emotion_specific_candidates = []
            generic_candidates = []
            for candidate in candidates:
                if self._track_has_personalized_emotion_signal(candidate, normalized_emotion):
                    emotion_specific_candidates.append(candidate)
                else:
                    generic_candidates.append(candidate)

            if emotion_specific_candidates:
                generic_cap = min(max(limit // 5, 1), 2)
                candidates = [
                    *emotion_specific_candidates,
                    *generic_candidates[:generic_cap],
                ]
            else:
                candidates = []

        result['tracks'] = candidates[:limit]
        result['ok'] = bool(result['tracks'])

        if result['sources_used']:
            logger.info(
                "Spotify user music candidates user=%s emotion=%s sources=%s count=%s",
                user.id,
                emotion,
                ','.join(result['sources_used']),
                len(result['tracks']),
            )

        return result


spotify_service = SpotifyService()
