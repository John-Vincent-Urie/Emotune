"""Decide whether free text says how the user feels before any model guesses.

/api/analyze/ runs these checks after the crisis check and before BERT:

1. gibberish    -- keyboard mash or no real words        -> ask again, no songs
2. non English  -- Tagalog or Taglish ("pagod na ako")  -> ask for English
3. emotion word -- "sad", "i'm so stressed", "😭"        -> that emotion, no BERT
4. off topic    -- questions, commands, facts, no self  -> ask again, no songs
5. vague        -- "meh", "idk", "fine"                  -> ask to clarify
6. otherwise BERT runs, and `model_result_is_unclear` rejects a low-confidence
   or near-tie answer the same way as (5).

Every rule is a word list or a simple pattern, so each decision can be traced to
the list entry that caused it. Song selection is English only (a user decision);
the crisis check before all of this still reads Tagalog.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from ml.emotion_classifier import EMOTION_KEYWORDS

STATUS_OK = 'ok'
STATUS_GIBBERISH = 'gibberish'
STATUS_OFF_TOPIC = 'off_topic'
STATUS_UNCLEAR = 'unclear'
STATUS_NON_ENGLISH = 'non_english'

CLARIFY_MESSAGES = {
    STATUS_GIBBERISH: "I couldn't understand that. Please tell me how you are feeling right now.",
    STATUS_OFF_TOPIC: 'Tell me how you are feeling right now.',
    STATUS_UNCLEAR: 'Please clarify what you feel right now.',
    STATUS_NON_ENGLISH: 'Please describe how you feel in English.',
}

ROUTE_EMOTION_WORD = 'emotion_word'
ROUTE_MODEL = 'model'

KNOWN_WORDS_PATH = Path(__file__).resolve().parent / 'data' / 'known_words.txt'

# Same tokenizer as ml_model/build_known_words.py, which builds the word list.
WORD_PATTERN = re.compile(r"[a-zñ]+(?:'[a-z]+)?")

# -- emotion words: a short input made only of these (plus fillers) is accepted
# as that emotion without running the model. Keys are the 13 model labels.
EMOTION_WORDS_EN = {
    'happy': (
        'happy', 'glad', 'joyful', 'cheerful', 'elated', 'delighted', 'thrilled',
        'ecstatic', 'overjoyed', 'blissful', 'jolly', 'good', 'great', 'happier',
        'joy', 'gleeful', 'giddy',
    ),
    'sad': (
        'sad', 'unhappy', 'down', 'blue', 'heartbroken', 'miserable', 'gloomy',
        'sorrowful', 'teary', 'crying', 'hurt', 'downcast', 'sadness', 'sadder',
        'devastated', 'broken hearted', 'brokenhearted', 'low',
    ),
    'angry': (
        'angry', 'mad', 'furious', 'pissed', 'pissed off', 'annoyed', 'irritated',
        'frustrated', 'livid', 'enraged', 'raging', 'fuming', 'irate', 'anger',
        'outraged', 'heated',
    ),
    'motivational': (
        'motivated', 'inspired', 'determined', 'driven', 'pumped', 'fired up',
        'energized', 'productive', 'ambitious', 'focused', 'unstoppable',
        'motivation', 'empowered',
    ),
    'fear': (
        'scared', 'afraid', 'fearful', 'frightened', 'terrified', 'nervous',
        'anxious', 'worried', 'panicking', 'panicky', 'uneasy', 'fear', 'spooked',
        'anxiety',
    ),
    'depressing': (
        'depressed', 'hopeless', 'numb', 'empty', 'despairing', 'despair',
        'depression', 'miserable inside', 'dead inside',
    ),
    'surprising': (
        'surprised', 'shocked', 'amazed', 'astonished', 'stunned', 'speechless',
        'wow', 'mind blown', 'mindblown', 'flabbergasted', 'surprise',
    ),
    'stressed': (
        'stressed', 'stressed out', 'overwhelmed', 'pressured', 'burnt out',
        'burned out', 'burnout', 'exhausted', 'tense', 'swamped', 'overworked',
        'stress', 'frazzled', 'drained',
    ),
    'calm': (
        'calm', 'relaxed', 'peaceful', 'chill', 'serene', 'at peace', 'tranquil',
        'mellow', 'at ease', 'calmer', 'relaxing',
    ),
    'lonely': (
        'lonely', 'alone', 'isolated', 'lonesome', 'abandoned', 'left out',
        'unloved', 'loneliness', 'all alone',
    ),
    'romantic': (
        'in love', 'romantic', 'lovesick', 'smitten', 'love struck', 'lovestruck',
        'affectionate', 'loved up', 'crushing',
    ),
    'nostalgic': (
        'nostalgic', 'sentimental', 'homesick', 'reminiscing', 'wistful',
        'nostalgia',
    ),
    'mixed': (
        'mixed', 'mixed feelings', 'conflicted', 'torn', 'bittersweet',
        'all over the place', 'confused',
    ),
}

# Emoji are language-neutral, so they are not part of the Tagalog hold.
EMOTION_EMOJI = {
    'happy': ('😊', '😄', '😁', '😀', '🙂', '😃', '🥳', '😆'),
    'sad': ('😭', '😢', '😞', '☹️', '🙁', '😔', '💔', '😿'),
    'angry': ('😡', '😠', '🤬', '😤'),
    'fear': ('😨', '😱', '😰', '😧'),
    'romantic': ('😍', '🥰', '😘', '❤️', '💕', '💖'),
    'calm': ('😌', '🧘'),
    'stressed': ('😩', '😫', '😵‍💫'),
    'surprising': ('😲', '😮', '🤯'),
}

# Words that can surround an emotion word without changing it.
FILLER_WORDS_EN = frozenset((
    'i', "i'm", 'im', 'am', 'me', 'feel', 'feeling', 'feels', 'felt', 'so',
    'very', 'really', 'super', 'quite', 'kinda', 'kind', 'of', 'a', 'bit',
    'little', 'pretty', 'just', 'rn', 'right', 'now', 'today', 'tonight',
    'totally', 'extremely', 'too', 'lately', 'currently', 'kind', 'sort', 'the',
    'most', 'soo', 'sooo', 'af', 'and', 'all', 'day', 'ever', 'been', "i've",
    'ive', 'getting', 'get', 'got', 'little', 'bit', 'honestly', 'literally',
    'tho', 'though', 'still', 'again', 'mood', 'is', 'my', 'like', 'such',
    'incredibly', 'deeply', 'truly', 'somewhat', 'slightly',
))

# Words that turn an emotion word around ("not happy"): never shortcut these.
NEGATION_WORDS_EN = frozenset((
    'not', 'no', 'never', "don't", 'dont', "isn't", 'isnt', "aren't", "wasn't",
    "didn't", "can't", 'cant', 'hardly', 'barely', 'without', 'nor', "ain't",
    'neither', 'less', 'stop', 'anymore',
))

# Inputs made only of these say no feeling yet: ask the user to clarify.
VAGUE_WORDS_EN = frozenset((
    'meh', 'ok', 'okay', 'k', 'fine', 'alright', 'idk', 'dunno', 'whatever',
    'nothing', 'normal', 'soso', 'hmm', 'hm', 'hmmm', 'eh', 'nah', 'average',
    'same', 'usual', 'neutral', 'unsure', 'something', 'stuff', 'things',
    'weird', 'off', 'blah', 'ugh', 'idc', 'nvm', 'whatevs', 'mid', 'bleh',
    'sure', 'yes', 'no', 'maybe', 'nope', 'yeah', 'yep', 'nothin',
))
VAGUE_PHRASES_EN = (
    'same as usual', 'as usual', 'same old', 'it is what it is', 'so so', 'not sure', "don't know", 'dont know', 'no idea', 'nothing much',
    'i guess', 'not much', "can't explain", 'cant explain', "don't care",
    'hard to say', 'not really sure', 'just there',
)

FIRST_PERSON_EN = frozenset((
    'i', "i'm", 'im', 'me', 'my', 'myself', 'mine', "i've", 'ive', "i'd",
    "i'll", 'ill', 'we', 'us', 'our', "we're", 'ourselves',
))

QUESTION_STARTS_EN = frozenset((
    'what', "what's", 'whats', 'who', "who's", 'where', 'when', 'why', 'how',
    "how's", 'which', 'whose', 'is', 'are', 'was', 'were', 'can', 'could',
    'will', 'would', 'should', 'do', 'does', 'did', 'has', 'have', 'shall',
))

COMMAND_STARTS_EN = frozenset((
    'play', 'give', 'recommend', 'suggest', 'show', 'tell', 'search', 'find',
    'open', 'make', 'write', 'calculate', 'compute', 'translate', 'define',
    'explain', 'list', 'name', 'list', 'put', 'start', 'stop', 'skip', 'queue',
    'set', 'turn', 'send', 'call', 'text', 'book', 'order', 'buy', 'download',
    'help', 'solve', 'convert', 'summarize', 'generate', 'create', 'add',
    'remove', 'delete', 'check', 'look',
))

# Emotional content that is not a bare emotion word: "my heart", "I cried".
AFFECT_CUES_EN = frozenset((
    'feel', 'feeling', 'feelings', 'felt', 'emotion', 'emotions', 'emotional',
    'mood', 'heart', 'cry', 'cried', 'tears', 'sob', 'sobbing', 'hate', 'love',
    'miss', 'missing', 'lost', 'broke', 'broken', 'fail', 'failed', 'failing',
    'died', 'death', 'dead', 'passed', 'breakup', 'dumped', 'cheated', 'fired',
    'rejected', 'tired', 'sick', 'hurts', 'hurting', 'pain', 'suffering',
    'grieving', 'grief', 'proud', 'excited', 'excitement', 'amazing', 'awesome',
    'terrible', 'awful', 'horrible', 'worst', 'best', 'cant', "can't",
    'falling', 'apart', 'scream', 'yay', 'yey', 'hooray', 'ugh', 'sigh',
    'sucks', 'crush', 'blessed', 'grateful', 'thankful', 'relieved', 'bored',
    'jealous', 'guilty', 'ashamed', 'embarrassed', 'insecure', 'disappointed',
    'heartbreak', 'lonely', 'stress', 'stressful', 'anxious', 'panic', 'cope',
    'coping', 'struggling', 'struggle', 'overthinking', 'worry', 'worrying',
    'life', 'everything', 'nobody', 'anyone', 'myself', 'promoted',
    'passed', 'graduated', 'engaged', 'married', 'birthday', 'vacation',
    # student life, the main source of stress in our users' messages
    'homework', 'exam', 'exams', 'deadline', 'deadlines', 'thesis', 'assignment',
    'assignments', 'quiz', 'grades', 'overtime', 'interview', 'scholarship',
    'results', 'accepted', 'admitted', 'hired',
    # how a feeling shows: face, body, voice
    'smile', 'smiled', 'smiling', 'laugh', 'laughed', 'laughing', 'giggle',
    'shaking', 'shake', 'trembling', 'sweating', 'butterflies', 'scream',
    'screamed', 'yell', 'yelled', 'shout', 'shouted', 'sighed', 'groan',
    # things done to us that carry a feeling
    'unfair', 'betrayed', 'insulted', 'ignored', 'blamed', 'bullied', 'praised',
    'ghosted', 'lied', 'excluded', 'humiliated', 'disrespected', 'surprised',
    'surprise',
))

# Emotion words that are also everyday words ("the sky is blue", "who won").
# They still work in the shortcut ("feeling blue" -> sad) but do not, on their
# own, make a sentence about feelings.
AMBIGUOUS_AFFECT_WORDS = frozenset((
    'blue', 'down', 'low', 'good', 'great', 'still', 'quiet', 'rest', 'dark',
    'power', 'push', 'goal', 'date', 'past', 'content', 'success', 'strength',
    'mixed', 'torn', 'off', 'busy', 'empty', 'heated', 'driven', 'focused',
    'chill', 'wow', 'remember', 'dream',
))

# -- Tagalog markers. Only words that are not also everyday English: "at",
# "man", "eh" are left out entirely, and the look-alikes below count only next
# to a clear marker, so "I may cry" and "my pa called" stay English. Names and
# places ("I miss Manila", "my lola") are not markers.
TAGALOG_MARKERS = frozenset((
    # pronouns
    'ako', 'ikaw', 'ka', 'ko', 'mo', 'siya', 'sya', 'niya', 'nya', 'kami',
    'tayo', 'kayo', 'sila', 'namin', 'natin', 'nila', 'ninyo', 'akin', 'sakin',
    'saakin', 'ating', 'amin', 'kanya', 'kita', 'tayong', 'akong',
    # particles, linkers, conjunctions
    'ang', 'ng', 'mga', 'nang', 'yung', 'iyong', 'ung', 'naman', 'nmn', 'lang',
    'lng', 'talaga', 'tlga', 'kasi', 'kase', 'kc', 'nga', 'po', 'opo', 'ba',
    'daw', 'raw', 'rin', 'pala', 'sana', 'pero', 'dahil', 'kapag',
    'pag', 'yata', 'kaso', 'tsaka', 'saka', 'parang', 'baka', 'siguro', 'ganun',
    'ganito', 'ganyan', 'ganon', 'diba', 'kaya',
    # time, place, demonstratives
    'ngayon', 'kanina', 'bukas', 'kahapon', 'ito', 'iyan', 'yan', 'yun', 'iyon',
    'dito', 'doon', 'dun', 'diyan', 'dyan', 'lagi', 'palagi', 'minsan',
    # negation, existence, wanting
    'hindi', 'wala', 'walang', 'meron', 'mayroon', 'ayoko', 'ayaw', 'gusto',
    'gustong', 'wag', 'huwag', 'pwede', 'puwede', 'kailangan', 'sige', 'oo',
    # question words
    'ano', 'sino', 'saan', 'bakit', 'paano', 'kailan', 'ilan', 'gaano',
    # intensifiers and exclamations
    'sobra', 'sobrang', 'grabe', 'medyo', 'naku', 'nako', 'hay', 'haay', 'ewan',
    'ang', 'napaka', 'talagang', 'lalo',
    # feelings and everyday content words
    'malungkot', 'lungkot', 'nalulungkot', 'masaya', 'saya', 'natutuwa', 'tuwa',
    'galit', 'nagagalit', 'naiinis', 'inis', 'nakakainis', 'badtrip', 'bwisit',
    'nakakabwisit', 'kinikilig', 'kilig', 'pagod', 'napapagod', 'nakakapagod',
    'takot', 'natatakot', 'kinakabahan', 'kaba', 'umiiyak', 'iyak', 'naiiyak',
    'nakakaiyak', 'masakit', 'sakit', 'nasasaktan', 'gulat', 'nagulat',
    'nakakagulat', 'kalma', 'payapa', 'panatag', 'hirap', 'nahihirapan',
    'mahirap', 'nag-iisa', 'mag-isa', 'magisa', 'iniwan', 'naiwan', 'mahal',
    'puso', 'buhay', 'trabaho', 'kaibigan', 'jowa', 'nanay', 'tatay', 'magulang',
    'gutom', 'antok', 'puyat', 'stressful', 'nakaka', 'nakakastress',
    'nakakatakot', 'nakakalungkot', 'masarap', 'maganda', 'pangit', 'tama',
    'ulit', 'gising', 'tulog', 'uwi', 'bahay', 'eskwela', 'klase',
    'naiinggit', 'selos', 'nagseselos', 'miss', 'namimiss', 'nami-miss',
    'na-miss', 'naalala', 'alaala', 'nakakamiss', 'lumbay', 'pighati', 'hiya',
    'nahihiya', 'kawawa', 'umaasa', 'pag-asa', 'motivated', 'ginaganahan',
    'tinatamad', 'tamad', 'walang gana', 'gana',
))
# Look-alikes: counted only when a clear marker is also present.
TAGALOG_WEAK_MARKERS = frozenset((
    'na', 'sa', 'pa', 'may', 'din', 'ni', 'si', 'kay', 'ay', 'nag', 'mag',
    'ma', 'mas', 'di', 'san', 'pang', 'kung',
))
# English words that would otherwise fall into the marker list above.
_ENGLISH_HOMOGRAPHS = frozenset(('miss', 'motivated', 'stressful', 'hay', 'kaya'))

# Asking for information or content, even about an emotion ("explain what
# anxiety is", "write a song about heartbreak"), is not saying how you feel --
# unless the user also talks about themselves ("why do I feel so sad").
REQUEST_FRAME_PATTERN = re.compile(
    r"^\s*(?:please\s+|pls\s+|can you\s+|could you\s+)?(?:"
    r"explain|define|describe|summari[sz]e|translate|"
    r"(?:write|compose|create|generate|make)\b.*\babout|"
    r"tell me (?:about|what|why|how)|give me (?:facts|information|info|a definition)|"
    r"what (?:is|are|does|do|was|were)|what's|whats|how (?:does|do|is|are)|"
    r"why (?:is|are|does|do)|(?:the )?meaning of"
    r")\b",
    re.IGNORECASE,
)
# "me" alone does not make a request personal: "tell me about anxiety".
SELF_WORDS_EN = FIRST_PERSON_EN - {'me'}

MATH_PATTERN = re.compile(r'\d+\s*[-+*/x^=]\s*\d+')
URL_PATTERN = re.compile(r'https?://|www\.|\.com\b')
REPEATED_LETTERS = re.compile(r'([a-z])\1{2,}')


@dataclass(frozen=True)
class InputCheck:
    """What the rules decided. `status` is the API's input_status, except
    'pass', which means BERT decides; `reason` names the rule that fired."""

    status: str
    reason: str
    emotion: str | None = None
    route: str | None = None
    has_affect: bool = True


@lru_cache(maxsize=1)
def known_words():
    words = set(KNOWN_WORDS_PATH.read_text(encoding='utf-8').split())
    for phrases in EMOTION_WORDS_EN.values():
        for phrase in phrases:
            words.update(phrase.split())
    words.update(FILLER_WORDS_EN, VAGUE_WORDS_EN, AFFECT_CUES_EN, FIRST_PERSON_EN)
    # Tagalog is a real language, not a keyboard mash: known here so it reaches
    # the non-English check instead of being called gibberish.
    words.update(TAGALOG_MARKERS, TAGALOG_WEAK_MARKERS)
    return frozenset(words)


@lru_cache(maxsize=1)
def _emotion_phrase_index():
    """(phrase tokens, emotion) pairs, longest first so 'in love' beats 'love'."""
    pairs = [
        (tuple(phrase.split()), emotion)
        for emotion, phrases in EMOTION_WORDS_EN.items()
        for phrase in phrases
    ]
    return tuple(sorted(pairs, key=lambda pair: -len(pair[0])))


@lru_cache(maxsize=1)
def _affect_vocabulary():
    """(single words, multi-word phrases) that make a sentence about feelings:
    our emotion words, the cues above, and the classifier's own keyword lists."""
    entries = set(AFFECT_CUES_EN)
    for phrases in EMOTION_WORDS_EN.values():
        entries.update(phrases)
    for keywords in EMOTION_KEYWORDS.values():
        entries.update(keyword.replace('-', ' ') for keyword in keywords)
    words = frozenset(
        entry for entry in entries
        if ' ' not in entry and entry not in AMBIGUOUS_AFFECT_WORDS
    )
    phrases = tuple(sorted(entry for entry in entries if ' ' in entry))
    return words, phrases


def _has_affect(tokens):
    words, phrases = _affect_vocabulary()
    if any(token in words for token in tokens):
        return True
    joined = f" {' '.join(tokens)} "
    return any(f' {phrase} ' in joined for phrase in phrases)


def _tokens(text):
    lowered = text.lower().replace('’', "'")
    return WORD_PATTERN.findall(lowered)


def _variants(token):
    """The token plus its repeated-letter squeezes: 'sooo' -> 'soo', 'so'."""
    variants = [token]
    if REPEATED_LETTERS.search(token):
        variants.append(REPEATED_LETTERS.sub(r'\1\1', token))
        variants.append(REPEATED_LETTERS.sub(r'\1', token))
    return variants


def _within_one_edit(a, b):
    """One insertion, deletion, substitution or swap of neighbours apart."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            i, j = diffs
            if a[i] == b[j] and a[j] == b[i]:
                return True  # 'lonley' -> 'lonely'
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
        else:
            i += 1
        j += 1
    return edits + (len(b) - j) <= 1


def _normalize_token(token, vocabulary):
    """The token as the lists know it: exact, squeezed, or a one-letter typo of
    an emotion word ('sadd', 'angy'). None when nothing matches."""
    if len(token) >= 3 and len(set(token)) == 1:
        return None  # one key held down: 'aaaaaa', 'zzzz'
    for variant in _variants(token):
        if variant in vocabulary:
            return variant
    if len(token) >= 4:
        for tokens, _emotion in _emotion_phrase_index():
            if len(tokens) == 1 and len(tokens[0]) >= 3 and _within_one_edit(token, tokens[0]):
                return tokens[0]
    return None


def _is_gibberish(text, tokens):
    if not tokens:
        # No letters at all: "!!!!", "12345". Arithmetic is handled as off topic.
        return not MATH_PATTERN.search(text)
    vocabulary = known_words()
    known = sum(1 for token in tokens if _normalize_token(token, vocabulary))
    if len(tokens) == 1:
        return known == 0
    return known / len(tokens) < 0.5


def _match_emotion_word(tokens):
    """The single emotion a short input names, or None."""
    if not tokens or len(tokens) > 6:
        return None
    vocabulary = known_words()
    normalized = [_normalize_token(token, vocabulary) or token for token in tokens]
    if any(token in NEGATION_WORDS_EN for token in normalized):
        return None
    found = set()
    remaining = list(normalized)
    index = 0
    leftovers = []
    while index < len(remaining):
        for phrase, emotion in _emotion_phrase_index():
            if tuple(remaining[index:index + len(phrase)]) == phrase:
                found.add(emotion)
                index += len(phrase)
                break
        else:
            leftovers.append(remaining[index])
            index += 1
    if len(found) != 1:
        return None
    if any(token not in FILLER_WORDS_EN for token in leftovers):
        return None
    return found.pop()


def _match_emoji(text):
    stripped = text.strip()
    found = {
        emotion
        for emotion, symbols in EMOTION_EMOJI.items()
        for symbol in symbols
        if symbol in stripped
    }
    if len(found) != 1:
        return None
    leftover = stripped
    for symbols in EMOTION_EMOJI.values():
        for symbol in symbols:
            leftover = leftover.replace(symbol, '')
    # Only emoji (and spacing or variation selectors) around them.
    if re.sub(r'[\s️‍!.]+', '', leftover):
        return None
    return found.pop()


def _is_vague(text, tokens):
    lowered = ' '.join(tokens)
    for phrase in VAGUE_PHRASES_EN:
        lowered = lowered.replace(phrase, ' ')
    rest = [token for token in lowered.split() if token not in FILLER_WORDS_EN]
    if not rest:
        return True
    return all(token in VAGUE_WORDS_EN for token in rest)


# Typed in lower case these are Tagalog particles ("tired na me", "sad sa
# school"); capitalised they are usually English abbreviations ("NA", "SA").
LOWERCASE_PARTICLES = frozenset(('na', 'sa'))


def _tagalog_markers(tokens, text=''):
    lowercase_words = set(WORD_PATTERN.findall(text.replace('’', "'")))
    strong = [
        token for token in tokens
        if (token in TAGALOG_MARKERS and token not in _ENGLISH_HOMOGRAPHS)
        or (token in LOWERCASE_PARTICLES and token in lowercase_words)
    ]
    weak = [
        token for token in tokens
        if token in TAGALOG_WEAK_MARKERS and token not in strong
    ]
    return strong, weak


def _is_non_english(tokens, text=''):
    """Mainly Tagalog, or Taglish with a clear Tagalog marker."""
    if not tokens:
        return False
    strong, weak = _tagalog_markers(tokens, text)
    if not strong:
        return False
    if len(strong) >= 2 or weak:
        return True
    # One clear marker is enough in a short message ("pagod ako" is two
    # markers; "so pagod" is one in two words), or when it carries a share of
    # a longer one.
    return len(tokens) <= 5 or len(strong) / len(tokens) >= 0.15


def _has_off_topic_signal(text, tokens):
    if MATH_PATTERN.search(text) or URL_PATTERN.search(text.lower()):
        return True
    if not tokens:
        return False
    if text.rstrip().endswith('?') or tokens[0] in QUESTION_STARTS_EN:
        return True
    return tokens[0] in COMMAND_STARTS_EN or (
        tokens[0] in ('please', 'pls', 'can', 'could') and len(tokens) > 1
        and tokens[1] in COMMAND_STARTS_EN | {'you'}
    )


def check_input(text):
    """Run rules 1-4 on text that already passed the crisis check."""
    tokens = _tokens(text)

    emoji_emotion = _match_emoji(text)
    if emoji_emotion:
        return InputCheck(STATUS_OK, 'emotion_emoji', emoji_emotion, ROUTE_EMOTION_WORD)

    if _is_gibberish(text, tokens):
        return InputCheck(STATUS_GIBBERISH, 'no_known_words')

    if _is_non_english(tokens, text):
        return InputCheck(STATUS_NON_ENGLISH, 'tagalog_markers')

    emotion = _match_emotion_word(tokens)
    if emotion:
        return InputCheck(STATUS_OK, 'emotion_word', emotion, ROUTE_EMOTION_WORD)

    vocabulary = known_words()
    normalized = [_normalize_token(token, vocabulary) or token for token in tokens]
    has_affect = _has_affect(normalized)
    has_first_person = any(token in FIRST_PERSON_EN for token in normalized)

    if _is_vague(text, normalized):
        return InputCheck(STATUS_UNCLEAR, 'vague_words', has_affect=has_affect)

    if REQUEST_FRAME_PATTERN.search(text) and not any(
        token in SELF_WORDS_EN for token in normalized
    ):
        return InputCheck(STATUS_OFF_TOPIC, 'information_request', has_affect=has_affect)

    if not has_affect:
        if _has_off_topic_signal(text, tokens):
            return InputCheck(STATUS_OFF_TOPIC, 'question_or_command', has_affect=False)
        if not has_first_person:
            return InputCheck(STATUS_OFF_TOPIC, 'not_about_self', has_affect=False)

    return InputCheck('pass', 'model', route=ROUTE_MODEL, has_affect=has_affect)


# -- step 6: is the model's answer clear enough to act on? Tuned on the dev rows
# of dataset/input_validation_eval.csv (see `manage.py eval_input_validation`).
# BERT is overconfident on plain facts ("i drank some water" -> calm 95%,
# "i just got home" -> surprised 95%), so confidence cannot tell a fact from a
# feeling. What can is whether the text has any emotional words: with them a
# modest bar is enough; without them the model must be near-certain.
MIN_MODEL_CONFIDENCE = 0.40
MIN_MODEL_MARGIN = 0.10
MIN_MODEL_CONFIDENCE_WITHOUT_AFFECT = 0.99
# Fallback sources mean BERT itself was below its own medium threshold.
TRUSTED_SOURCES = ('bert', 'goemotions')


def model_result_is_unclear(result, check):
    """True when the classifier's answer is a guess rather than a reading."""
    if not isinstance(result, dict):
        return True
    if result.get('prediction_strategy') == 'system_fallback':
        # The classifier crashed: serve the "mixed" list as before rather than
        # bounce every message during an outage.
        return False
    if result.get('prediction_source') not in TRUSTED_SOURCES:
        return True
    confidence = float(result.get('confidence') or 0.0)
    margin = float(result.get('confidence_margin') or 0.0)
    if check is not None and not check.has_affect:
        return confidence < MIN_MODEL_CONFIDENCE_WITHOUT_AFFECT
    return confidence < MIN_MODEL_CONFIDENCE or margin < MIN_MODEL_MARGIN


@dataclass(frozen=True)
class Decision:
    """The analyze endpoint's answer for text that passed the crisis check.
    `result` is the classifier output when the model ran."""

    status: str
    reason: str
    route: str | None = None
    emotion: str | None = None
    result: dict | None = None


def decide_after_crisis(text, predict):
    """Rules, then the model if needed. `predict(text)` runs the classifier.

    Text with concern-tier language skips the clarify rules and goes straight
    to the model, exactly as before this check existed, so its gentle check-in
    is never replaced by "please clarify".
    """
    from .safety import assess_concern

    check = None if assess_concern(text) else check_input(text)
    if check is not None and check.status not in (STATUS_OK, 'pass'):
        return Decision(check.status, check.reason)
    if check is not None and check.route == ROUTE_EMOTION_WORD:
        return Decision(STATUS_OK, check.reason, ROUTE_EMOTION_WORD, check.emotion)

    result = predict(text)
    if check is not None and model_result_is_unclear(result, check):
        return Decision(STATUS_UNCLEAR, 'low_model_confidence', result=result)
    reason = 'concern_guard' if check is None else 'model'
    return Decision(STATUS_OK, reason, ROUTE_MODEL, result.get('emotion'), result)
