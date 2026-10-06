"""Crisis-risk detection for free-text input.

This is a first-line safety net, not a clinical screening tool: a phrase match
against known self-harm/suicide language, run before the text ever reaches the
emotion classifier or a music recommendation. See docs/music_therapy_guidelines.md
("Known issues to fix", #4) for why this exists as a separate concern from emotion
-> music mapping -- an emotion label alone (even "depressing") is not a reliable
proxy for this kind of risk, so this checks the text itself.

False negatives matter more than false positives here: phrases are kept broad
enough to catch common phrasing (including Filipino/Taglish, since the app's own
curated content in docs/music.md targets a Philippine audience), and multi-word so
casual, non-risk speech ("dying laughing", a song lyric) doesn't constantly trip it.
"""
from __future__ import annotations

import re
import unicodedata

from django.conf import settings

RISK_CRISIS = "crisis"
RISK_CONCERN = "concern"

# Narrow exits for everyday sentences: "no point living in Manila", "no reason
# to go on the trip", "no reason to wake up early". Deliberately not "in this"
# or "with this": "no point in living in this pain" is the real thing.
_BENIGN_LIVING = (
    r"(?! (?:in|at|near) (?:the |a |this |my |our )?(?:city|manila|metro manila|qc|cebu|davao|province|dorm|dormitory|"
    r"house|apartment|condo|area|country|philippines|ph|states|abroad|town|village|neighborhood|subdivision)\b"
    r"| with (?:my |our |your |the )?(?:parents|roommates?|family|mom|dad|mother|father|partner|boyfriend|girlfriend|bf|gf|"
    r"friends?|siblings?|them|him|her|people|someone)\b"
    r"| on (?:a|the|this|that) (?:trip|date|vacation|tour|break|walk|diet|ride|run|holiday|hike)\b"
    r"| (?:so )?early\b| late\b)"
)

# "nag-overdose ako sa kape" (too much coffee) is not an overdose.
_NOT_FOOD_OVERDOSE = (
    r"(?!(?: \w+){0,2} (?:sa|on|ng|of|with) (?:kape|coffee|caffeine|sugar|chocolate|milk ?tea|sweets|carbs|"
    r"k-?pop|anime|netflix|memes|content|love|kilig))"
)

_CRISIS_PHRASES = [
    # English
    r"kill(?:ing)? myself",
    r"end(?:ing)? my (?:own )?life",
    r"take my (?:own )?life",
    r"want(?:ed|s)? to die(?! (?:my|your|her|his|the) hair)",
    r"wish(?:ed)? i (?:was|were) dead",
    r"don'?t want to (?:live|be alive|wake up)",
    r"no reason to (?:live|go on)",
    r"better off dead",
    r"end it all(?! with)",
    r"can'?t go on (?:living|anymore)",
    r"(?:hurt|harm|cutt?ing)(?:ing)? myself",
    r"self[- ]?harm",
    r"suicidal",
    r"suicide(?! (?:prevention|awareness|squad))",
    # Indirect ideation -- the forms people actually type. Missed in QA before
    # these were added (2026-10-04); each has a test in test_crisis_safety.py.
    r"better off without me",
    r"no (?:point|reason) (?:in |to )?(?:living|live|being alive|going on|go on)\b" + _BENIGN_LIVING,
    r"(?:life|living) (?:is not|isn'?t|not) worth (?:it|living)",
    r"not worth living",
    r"(?:disappear|vanish) forever",
    r"(?:want(?:ed|s)?|wish) to (?:not exist|stop existing)",
    r"(?:wish|want|hope|rather)\b[^.!?]{0,40}\b(?:never|not) (?:to )?wake up(?! (?:early|late|the|my|him|her|them|at|before|until))",
    r"\bunalive (?:myself|me)\b",
    r"\bkms\b",
    # Possible overdose in progress: never answer this with a playlist.
    r"(?:took|taken|swallowed|ate) (?:a bunch of|too many|all (?:of )?(?:my|the)|a lot of|lots of|a handful of|a whole (?:bottle|pack) of) (?:pills|meds|medicine|medication|tablets|sleeping pills|painkillers)",
    r"overdos(?:e|ed|ing)" + _NOT_FOOD_OVERDOSE,
    # Filipino / Taglish
    r"gusto ko(?: na)?(?:ng)? mamatay",
    r"papatayin ko(?: na lang)? (?:ang )?sarili(?: ko)?",
    r"magpapakamatay",
    r"ayoko na (?:sa )?buhay",
    r"ayoko na(?:ng)? mabuhay",
    r"wala na akong dahilan(?: para)? mabuhay",
    r"wala nang saysay (?:ang )?buhay",
    r"sana (?:hindi|di) na (?:ako )?magising",
    r"ayoko na(?:ng)? magising",
    r"mas (?:okay|ok|mabuti|maganda|masaya) (?:pa )?(?:sila )?(?:kung|kapag|pag) wala (?:na )?ako",
    r"mawala na (?:lang )?ako(?: (?:ng tuluyan|forever))?",
    r"(?:uminom|ininom|nilunok) (?:ako )?(?:ng )?(?:maraming|madaming|isang banig na|lahat ng) (?:gamot|pills|tableta)",
]

_CRISIS_PATTERN = re.compile("|".join(_CRISIS_PHRASES), re.IGNORECASE)

# --- Normalized, composed matching --------------------------------------------
#
# The literal phrases above only catch the wording someone thought of in advance:
# in QA, "I wanna die" and "I'm going to jump off the building tonight" both got
# a playlist. Below, text is first normalized (case, apostrophes, elongation,
# chat spellings, Tagalog shorthand), then matched as *intent + death/self-harm*
# with a few words of slack in between, plus method, plan and timeline cues. It
# runs alongside the literal list, never instead of it.
#
# The eval sets in api/safety_eval/ measure this: `manage.py eval_crisis_detection`.

SEVERITY_CRISIS = "crisis"
SEVERITY_IMMINENT = "imminent"

# Whole-token rewrites applied after lowercasing and stripping punctuation.
_TOKEN_REWRITES = {
    # English chat spelling
    "wanna": "want to", "wana": "want to", "wnna": "want to", "wan": "want",
    "gonna": "going to", "gona": "going to", "finna": "going to",
    "imma": "im going to", "ima": "im going to",
    "gotta": "got to", "tryna": "trying to", "boutta": "about to",
    "2": "to", "u": "you", "ur": "your", "rn": "right now",
    "tonite": "tonight", "2nite": "tonight", "2night": "tonight", "tmrw": "tomorrow", "tmr": "tomorrow",
    "wnat": "want", "wnt": "want", "whant": "want", "wamt": "want",
    "kil": "kill", "kll": "kill", "kilk": "kill", "kms": "kill myself", "kmself": "kill myself",
    "myslf": "myself", "myelf": "myself", "mself": "myself", "myslef": "myself", "mysef": "myself",
    "myaelf": "myself", "mysefl": "myself", "lyf": "life", "lyfe": "life", "liv": "live",
    "unalive": "kill myself", "unaliving": "killing myself",
    "selfharm": "self harm", "sh": "self harm",
    "suicde": "suicide", "sucide": "suicide", "suiside": "suicide", "siucide": "suicide", "suicie": "suicide",
    "ctb": "suicide", "selfdelete": "kill myself",
    "dye": "die", "di3": "die",
    "everythin": "everything", "dei": "die", "bout": "about", "abt": "about",
    "tonights": "tonight", "todays": "today", "tomorrows": "tomorrow",
    "thinkin": "thinking", "thinkn": "thinking", "endin": "ending", "killin": "killing", "livin": "living",
    "goin": "going", "tryin": "trying", "cuttin": "cutting", "hurtin": "hurting", "dyin": "dying",
    "plannin": "planning", "jumpin": "jumping", "takin": "taking", "hangin": "hanging", "burnin": "burning",
    "existin": "existing", "leavin": "leaving", "nothin": "nothing", "wantin": "wanting",
    "yeet": "throw", "yeeting": "throwing", "nagoverdose": "nag overdose",
    # Tagalog shorthand
    "q": "ko", "aq": "ako", "aqo": "ako", "ak": "ako", "ko": "ko",
    "n": "na", "nlng": "na lang", "nlang": "na lang", "nalang": "na lang", "nalng": "na lang",
    "lng": "lang", "nko": "na ko", "nako": "na ako",
    "wla": "wala", "tlga": "talaga", "tlaga": "talaga", "mwala": "mawala", "kwnta": "kwenta", "bhay": "buhay",
    "sna": "sana", "pra": "para", "d": "di", "sawangsawa": "sawang sawa",
    "gsto": "gusto", "gustu": "gusto", "gus2": "gusto", "gustong": "gusto",
    "mmatay": "mamatay", "mamatai": "mamatay", "mamatey": "mamatay", "mamtay": "mamatay", "mmtay": "mamatay",
    "mgpakamatay": "magpakamatay", "magpakamtay": "magpakamatay", "mgpakamtay": "magpakamatay",
    "mbuhay": "mabuhay", "mabuhai": "mabuhay", "mabuhy": "mabuhay",
    "ayuko": "ayoko", "ayoq": "ayoko", "ayko": "ayoko",
    "magsuicide": "mag suicide",
}
_TOKEN_PHRASE_REWRITES = [
    (re.compile(r"\bmy self\b"), "myself"),
    (re.compile(r"\bmyself (?:myself|me)\b"), "myself"),
    (re.compile(r"\bsewer ?slide\b"), "suicide"),
    (re.compile(r"\bcommit (?:die|sudoku|seppuku|toaster bath|self delete|neck rope|not alive)\b"), "commit suicide"),
    (re.compile(r"\btoaster bath\b"), "suicide"),
    (re.compile(r"\b(?:self delete|delete myself|uninstall myself)\b"), "kill myself"),
    (re.compile(r"\bself ?harm(?:ing|ed)?\b"), "self harm"),
    (re.compile(r"\bsu ?suicide\b"), "suicide"),
    (re.compile(r"\bayaw ko\b"), "ayoko"),
    (re.compile(r"\bjump rope\b"), "jumprope"),
]


def _collapse_elongation(token: str) -> list[str]:
    """Spellings to try for a stretched word: "dieeeee" -> "die", "killll" -> "kill"."""
    if not re.search(r"(.)\1\1", token):
        return [token]
    two = re.sub(r"(.)\1{2,}", r"\1\1", token)
    one = re.sub(r"(.)\1{2,}", r"\1", token)
    return [one, two]


def normalize_for_safety(text: str) -> str:
    """Lowercased, punctuation-free, slang-expanded text for the composed patterns.

    Clause breaks become " | " so a window cannot run across sentences
    ("the exam killed me. I want to sleep" must not read as one thought).
    """
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = re.sub(r"[​-‍﻿]", "", text)
    text = text.replace("'", "")  # don't -> dont, i'm -> im
    text = re.sub(r"(?<=\w)-(?=\w)", "", text)  # self-harm -> selfharm, su-suicide
    text = re.sub(r"[.!?;,\n]+", " | ", text)
    text = re.sub(r"[^\w|]+", " ", text)

    tokens = []
    for raw in text.split():
        candidates = _collapse_elongation(raw)
        # Prefer a spelling that is a known word; "diee" is caught by the 2-char form.
        chosen = next((c for c in candidates if c in _TOKEN_REWRITES), candidates[-1])
        if chosen.startswith("die") and re.fullmatch(r"die+", chosen):
            chosen = "die"
        tokens.append(_TOKEN_REWRITES.get(chosen, chosen))
    text = " ".join(tokens)
    for pattern, replacement in _TOKEN_PHRASE_REWRITES:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


# Up to N words of slack inside one clause ("I really just want to die").
def _gap(n: int) -> str:
    return rf"(?:[^\s|]+ ){{0,{n}}}"


_WANT = (
    # Not when a thing is the subject: "my battery is about to die".
    r"(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bits )(?<!\bwere )(?:want(?:s|ed)?(?: to)?|wish(?:ed)?(?: (?:to|i (?:could|would)))?|going to|will|ill|"
    r"plan(?:ning)?(?: to| on)?|decided to|ready to|about to|should|need to|"
    r"thinking (?:about|of)|think about|tempted to|feel like|might|gusto|balak|sana|handa|"
    r"tried to|try to|trying to|attempted to|attempt to|plano|naiisip|iniisip)"
)
_DEATH = (
    r"(?:die(?!(?: [^\s|]+){0,2} (?:hair|shirt|clothes|fabric|dress|eggs))|be dead|"
    r"kill(?:ing)? myself|"
    # "end it with him" and "end things with my girlfriend" are breakups.
    r"end(?:ing)? (?:my life|my own life|this life|myself|(?:it all|it|everything|things)(?! with| between| on a| off))|"
    r"off(?:ing)? myself|take my (?:own )?life|stop existing|not exist|not be (?:here|alive|around) (?:anymore|na|forever)|"
    r"suicide(?! prevention| awareness| squad)|commit suicide|"
    r"(?:hurt(?:ing)?|harm(?:ing)?|burn(?:ing)?|hit(?:ting)?|punch(?:ing)?|starv(?:e|ing)|scratch(?:ing)?) myself|"
    r"cut(?:ting)? myself(?! a | an | some )|"
    r"hang(?:ing)? myself|shoot(?:ing)? myself|drown(?:ing)? myself|stab(?:bing)? myself|overdose" + _NOT_FOOD_OVERDOSE + "|"
    r"bleed (?:out|to death)|(?:go to |fall )?sleep and (?:not|never) wake up|"
    r"end(?:ing)? (?:my|this) (?:suffering|pain|misery|existence|journey|story)|patay na (?:lang )?ako|"
    r"rope(?! (?:in|into|off|him|her|them|someone|people|a|the)\b)|"
    r"(?:eternal|permanent) (?:sleep|rest)|rest in peace|go to heaven (?:now|na|already|soon)|"
    r"(?:be with|join) [^\s|]+ (?:[^\s|]+ )?in heaven|makasama (?:[^\s|]+ ){0,2}sa langit|"
    r"mamatay|magpakamatay|mag suicide|mawala(?: na)?(?: lang)?(?: ako)?(?= \||$| forever| ako| sa mundo| na sa mundo)|"
    r"kunin na(?: lang)? ako|(?:matapos|tapusin) (?:na )?(?:ang )?lahat(?! ng))"
)
_HIGH_PLACE = r"(?:building|bridge|roof|rooftop|balcony|window|ledge|cliff|overpass|floor|tower|tulay|bubong|bintana)"
_PILLS = r"(?:pills?|meds|medicines?|medications?|tablets?|gamot|tableta|sleeping pills|painkillers|paracetamol|ibuprofen)"
_MANY = r"(?:all|every|whole bottle of|entire bottle of|bunch of|handful of|too many|lahat ng|maraming|madaming|isang banig na)"

# "No point / no reason / no will to live", in its many wordings.
_NO_LEAD = (
    r"(?:no|dont see (?:a|any|the)|cant see (?:a|any|the)|dont have (?:a|any)|cant find (?:a|any|the)|"
    r"theres no|there is no|there isnt (?:a|any)|lost (?:my|the|all)(?: of my)?|losing (?:my|the)|"
    r"have no|got no|zero|without (?:a|any)|not (?:a|any))"
)
_NO_NOUN = r"(?:point|reason|purpose|will|desire|meaning|use|sense)"
_LIVE = (
    r"(?:living|live|being alive|be alive|staying alive|stay alive|going on|go on|existing|exist|"
    r"carry on|carrying on|survive|surviving|wake up|waking up)"
)
_LIVE_STRONG = r"(?:living|live|being alive|staying alive|stay alive|going on|go on|existing|exist|survive)"

_CRISIS_COMPOSED = [
    # intent + death or self-harm, with slack: "i really just want to die"
    rf"\b{_WANT} {_gap(4)}{_DEATH}\b",
    # first-person self-harm or suicide with no intent verb needed
    r"\b(?:kill(?:ing|ed)?|off(?:ing|ed)?|hurt(?:ing)?|harm(?:ing|ed)?|hang(?:ing|ed)?|"
    r"shoot(?:ing)?|drown(?:ing)?|stab(?:bing|bed)?|poison(?:ing|ed)?) myself\b",
    r"\bcut(?:ting)? myself(?! a | an | some )\b",
    r"\b(?:keep|started|been|nag) cut(?:ting)?\b(?! (?:class|classes|school|hair|my hair))",
    r"\bcut(?:ting)? (?:again|ulit)\b",
    r"\b(?:keep|kept|started|been|always|still|sometimes|nag) (?:on )?(?:burning|hitting|punching|scratching|starving|"
    r"cutting|hurting|biting|bruising) (?:myself|my (?:arms?|wrists?|legs?|thighs?|skin))\b",
    r"\bself harm\b", r"\bsuicid(?:e|al)\b(?! squad| prevention| awareness)",
    r"\b(?:slit|cut|slash)(?:ting)? my wrists?\b",
    r"\bend(?:ing)? (?:my|my own) life\b", r"\bend it all\b(?! with)",
    r"\bend ko na (?:life|buhay) ko\b",
    r"\b(?:i|ill|i will|im going to|going to|gonna) end it\b(?! with| between| on a| off)",
    r"\bdone with (?:life|living|being alive)\b",
    # no point / no reason / no will to live
    rf"\b{_NO_LEAD} {_gap(1)}{_NO_NOUN} (?:in |of |to |for )?(?:me |me to |anyone )?(?:to )?(?:even )?"
    rf"(?:keep |keep on |continue |still )?{_LIVE}\b{_BENIGN_LIVING}",
    rf"\b(?:whats|what is|why) (?:even )?(?:the )?(?:point|reason|use|purpose) (?:of |in |to )?(?:even )?"
    rf"(?:keep |keep on |continue |still )?{_LIVE_STRONG}\b{_BENIGN_LIVING}",
    rf"\bwhy (?:should|would|do|must|even|bother) (?:i )?(?:even )?(?:bother )?(?:to )?"
    rf"(?:keep |keep on |continue |still )?{_LIVE_STRONG}\b{_BENIGN_LIVING}",
    # passive ideation
    r"\b(?:wish|rather|better off|might as well) {_gap}(?:be |been |was |were )?dead\b".replace("{_gap}", _gap(3)),
    r"\bbetter off without me\b",
    r"\b(?:dont|do not|dont really|never|doesnt|does not|doesnt really|didnt) want to (?:live|be alive|exist|wake up|be here anymore|be here na|be around anymore)\b",
    r"\bnever wake up\b(?! early| late)",
    rf"\b(?:better|happier|easier|fine|okay|ok|lighter|good)(?: off)? {_gap(4)}if i (?:was|were|am) "
    r"(?:gone|dead|not here|not around|not alive|never born)\b",
    rf"\b(?:better|happier|easier|fine|okay|ok|lighter|good)(?: off)? {_gap(4)}if i "
    r"(?:(?:wasnt|werent) (?:here|around|alive|born|in (?:the|their) (?:picture|lives?))|didnt exist|never existed|disappeared|died)\b",
    r"\b(?:would|will|wouldnt|wont) (?:notice|care|miss me) if i (?:died|was dead|was gone|disappeared)\b",
    r"\bif i (?:died|was dead|was gone)\b",
    r"\bwant (?:it all|everything|my life|it) to (?:be over|end|stop)\b",
    r"\b(?:life|living) (?:is not|isnt|aint|not) worth (?:it|living)\b",
    r"\b(?:tired|sick|sick and tired) of (?:living|being alive|existing|staying alive)\b",
    rf"\b(?:nobody|no one|noone|walang) {_gap(3)}(?:miss|care|notice|remember|mamimiss|makakamiss|iiyak) {_gap(3)}"
    r"(?:when|if|after|pag|kapag|kung) (?:im |i am |i was )?(?:gone|dead|i die|i died|wala na ako|patay na ako)\b",
    rf"\b{_WANT} {_gap(4)}(?:drive|crash|swerve|steer|walk|step) {_gap(3)}(?:off (?:a |the )?(?:road|cliff|bridge|overpass|highway)|"
    r"into (?:a |the )?(?:wall|tree|truck|pole|traffic|river|sea|ocean|oncoming))\b",
    # Wishing not to exist (C-SSRS item 1) is crisis, not concern.
    r"\b(?:wish|hope|sana)(?: that)? (?:i|ako) (?:wasnt|werent|was not|were not|hadnt been|had never been|was never|were never|never) "
    r"(?:alive|born|here|around)\b",
    r"\b(?:wish|hope|sana) {g}(?:never|didnt|did not|wouldnt) (?:wake|woke) up\b(?! early| late)".replace("{g}", _gap(3)),
    r"\bsana (?:hindi|di) (?:na )?(?:lang )?(?:ako )?(?:ipinanganak|pinanganak|isinilang|nabuhay)\b",
    rf"\b(?:want|wish|gusto|sana) {_gap(3)}(?:sleep|matulog|fall asleep) (?:forever|habambuhay|panghabambuhay)\b"
    r"(?! (?:this|next|on|during|after|until|til)\b)",
    rf"\b(?:fine|okay|ok|wouldnt mind|dont mind|dont care|wouldnt care|happy|glad|be nice|good) if {_gap(2)}"
    rf"(?:car|bus|truck|train|jeep|something|someone|lightning|plane) {_gap(1)}(?:hit|hits|killed|kills|ran over|runs over|took|takes) me\b",
    r"\b(?:whats|what is) (?:even )?(?:the )?(?:point|use|purpose) (?:of |in )?(?:me |my )"
    r"(?:being here|being alive|living|existing|existence|life)\b",
    r"\b(?:dont|do not|not) (?:plan|planning|intend|intending|expect|expecting) (?:on|to) (?:be|being) (?:here|around|alive)\b",
    r"\bif i (?:jumped|disappeared|killed myself|ended it|left forever|stopped existing|wasnt here)\b",
    r"\bwhat if i (?:just )?(?:stopped existing|stop existing|disappeared|died|wasnt here|didnt exist|ended it)\b",
    r"\b(?:not|no longer) (?:afraid|scared) (?:to die|of dying|of death)\b",
    r"\bnothing (?:left )?to live for\b|\bno (?:one|body) to live for\b",
    r"\b(?:better|happier|fine|okay|ok|alright|good) (?:off )?without me\b",
    r"\bcant (?:keep|go on|continue|carry on) (?:living|existing|being alive)\b",
    r"\bcheck(?:ing|ed)? out (?:for good|permanently|of life|early|of this world)\b",
    r"\bcut(?:ting)? (?:deeper|again|ulit|more and more)\b",
    rf"\b(?:burned|burnt|cut|hit|punched|scratched|hurt|bruised|stabbed|sliced) (?:my |myself )?{_gap(1)}"
    r"(?:on purpose|intentionally|deliberately|sinadya|sadya)\b",
    r"\b(?:magpapasagasa|magpasagasa|nagpasagasa|pasagasa|pasasagasa)\b",
    r"\bpara (?:na )?(?:mamatay|magpakamatay|hindi na magising|di na magising)\b",
    r"\bpara (?:tapusin|matapos) na(?: ang)?(?: lahat| buhay ko)?(?= ?\||$)",
    rf"\b(?:sawa|sawang sawa|pagod|suya)(?: na)? (?:ako|ko|akong|kong) {_gap(1)}(?:pag ?)?mabuhay\b",
    rf"\b(?:mas )?(?:mabuti|okay|ok|maganda|better|masaya)(?: pa| pang)? {_gap(2)}(?:patay|mamatay|wala) (?:na )?(?:lang )?ako\b"
    r"(?! sa (?!buhay|mundo))",
    # wishing for death without an intent verb; a negation inside means it is not
    r"\b(?:hope|hoping|pray|praying|wish)(?: that)? (?:i|ako) (?:(?!dont|doesnt|wont|never|not|hindi|di)[^\s|]+ ){0,2}"
    r"(?:die|dies|get hit|get run over|get killed|(?:dont|never|wont|do not|wouldnt) wake up(?! early| late| on time| the| my| at| before| until))\b",
    rf"\b(?:wish|hope|hoping|pray|praying|want|sana)(?: that)? {_gap(4)}(?:car|bus|truck|train|jeep|jeepney|someone|"
    rf"somebody|something|god|lord|the universe|lightning) {_gap(2)}(?:would |will |to |could |please )?"
    r"(?:hit|hits|run over|runs over|kill|kills|take|takes|end|ends) me\b(?! up| back| with| home| out| to| there| along)",
    r"\b(?:god|lord|panginoon) (?:please )?(?:just )?(?:take|end) me\b(?! home| to| there| with| back| out| away)",
    # Tagalog / Taglish
    r"\bpakamatay\b|\bmagpakamatay\b|\bmagpapakamatay\b|\bnagpakamatay\b",
    r"\b(?:ayoko|hindi ko gusto|di ko gusto|hindi ko na gusto|di ko na gusto) {g}mabuhay\b".replace("{g}", _gap(3)),
    # Someone else's words: "ayaw na niyang mabuhay" (they don't want to live anymore).
    r"\bayaw (?:na |nang )?(?:niyang|nyang|niya|nya|nilang|nila) {g}mabuhay\b".replace("{g}", _gap(2)),
    r"\bpagod na (?:ako|ko|akong|kong) (?:pag ?)?mabuhay\b",
    rf"\bwala(?:ng)? {_gap(3)}(?:gana|ganang|dahilan|rason|reason|point|motibasyon|saysay) {_gap(2)}"
    r"(?:mabuhay|mag ?live|magpatuloy|sa buhay)\b",
    r"\bbakit pa (?:ba )?(?:ako |ko )?(?:mabubuhay|mabuhay|nabubuhay|magpapatuloy)\b",
    r"\b(?:patayin|papatayin|pinatay|patay) {g}sarili\b".replace("{g}", _gap(4)),
    r"\b(?:saktan|sinasaktan|sasaktan|sinaktan|nanakit) {g}sarili\b".replace("{g}", _gap(4)),
    rf"\b(?:sugatan|sinusugatan|sinugatan|susugatan|pinupukpok|pukpukin|pinapaso|pinaso|papasuin) {_gap(3)}"
    r"(?:sarili|braso|pulso|wrist|hita|kamay|balat|ulo)\b",
    r"\b(?:tapusin|tatapusin|tinapos) {g}buhay\b".replace("{g}", _gap(4)),
    r"\bwala (?:na|nang) (?:saysay|silbi|kwenta) (?:ang )?(?:mabuhay|buhay)\b",
    rf"\b(?:mas )?{_gap(2)}(?:okay|ok|mabuti|maganda|masaya|magaan|tahimik|maayos) {_gap(3)}(?:kung|kapag|pag) "
    r"wala (?:na )?ako\b(?! sa (?!buhay|mundo))",
    r"\b(?:magbigti|magbibigti|nagbigti|bibigti|bigti)\b",
    r"\b(?:hiwa|hiniwa|hihiwain|laslas|naglaslas|maglaslas|lalaslasin) {g}(?:pulso|wrist|braso|arm)\b".replace("{g}", _gap(3)),
    r"\bsuicide na (?:lang )?(?:ako|ko)\b",
    r"\bkill myself na\b",
    r"\bkunin (?:mo )?na (?:lang )?(?:po )?ako\b",
    r"\b(?:sana|gusto ko)(?: na)?(?: lang)?(?: na)? (?:mabangga|masagasaan|mabundol|madisgrasya|maaksidente|tamaan ng kidlat)\b",
]

# Plan, method, preparation or timeline: any one of these alongside crisis
# language makes it high severity, and the method and preparation patterns are
# crisis on their own.
_METHOD = [
    rf"\b(?:jump|jumping|tatalon|tumalon|talon|throw myself|throwing myself|fling myself|launch myself) {_gap(4)}"
    rf"(?:off |from |sa |mula sa )?{_gap(2)}{_HIGH_PLACE}\b",
    rf"\b(?:handa|nakahanda|ready|prepared|set up|tied) {_gap(2)}(?:lubid|rope|noose|lason|poison|kutsilyo|blade)\b",
    rf"\b(?:lubid|rope|noose) {_gap(2)}(?:ready|handa|nakahanda|set up)\b",
    rf"\b(?:ilang|gaano (?:karami|karaming|kadami|kadaming)) {_gap(3)}(?:tableta|pills?|gamot|biogesic|paracetamol|neozep|sleeping pills) "
    rf"{_gap(3)}(?:para mamatay|para (?:hindi|di) na magising|para matapos)\b",
    rf"\b(?:take|taking|swallow|swallowing|overdose on|inumin|iinumin|inom|inomin|lunukin|lulunukin|lalaklakin|laklakin|ininom|nilunok|took|swallowed|uubusin|ubusin|inubos) {_gap(3)}{_MANY} {_gap(2)}{_PILLS}\b",
    rf"\b(?:lalaklakin|lulunukin|iinumin|inumin) {_gap(2)}lahat {_gap(2)}{_PILLS}?",
    rf"\b(?:have|got|saved|stocked|collected) {_gap(2)}(?:the |my |enough |all )?{_PILLS} {_gap(1)}(?:ready|saved|up)\b",
    rf"\b(?:stockpil(?:e|ed|ing)|hoard(?:ed|ing)?|saving up|saved up|been saving|nagiipon|nag iipon|nagipon|inipon|iniipon) {_gap(2)}{_PILLS}\b",
    r"\b(?:bought|got|have|tied|made) (?:a |the |my )?(?:rope|noose)\b",
    r"\b(?:knife|blade|razor|gun) {g}(?:on myself|myself)\b".replace("{g}", _gap(8)),
    r"\buse it on myself\b",
    rf"\b(?:standing|sitting|im|i am) (?:on|at) (?:the |a |this )?(?:edge of the )?(?:{_HIGH_PLACE}|edge|railing)\b",
    r"\b(?:hang(?:ing|ed)? myself|bigti|magbigti|magbibigti)\b",
    r"\b(?:magpapasagasa|magpasagasa|nagpasagasa|pasagasa|pasasagasa)\b",
    r"\b(?:slit|slash) my wrists?\b",
    r"\b(?:hiwa|hiniwa|hihiwain|laslas|naglaslas|maglaslas|lalaslasin) {g}(?:pulso|wrist)\b".replace("{g}", _gap(3)),
    r"\b(?:drown|shoot) myself\b",
    # drinking poison (silver cleaner and muriatic acid are known methods here)
    rf"\b(?:inom|iinom|iinumin|inumin|ininom|uminom|drink|drinking|drank|swallow|swallowed|take|took|taking) {_gap(4)}"
    r"(?:lason|poison|rat poison|bleach|zonrox|muriatic|silver cleaner|pesticide|insecticide|baygon|paraquat|antifreeze)\b",
    rf"\b(?:took|taken|swallowed|ate|ininom|uminom|nilunok) (?:like |around |about |mga )?(?:[1-9][0-9]+|twenty|thirty|forty|fifty|a hundred|dozens of) {_gap(1)}{_PILLS}\b",
    r"\bcrash {g}on purpose\b".replace("{g}", _gap(3)),
    r"\b(?:jump|step|walk|throw myself|lie down|humiga|tumalon|tatalon) {g}(?:in front of|onto|sa harap ng) (?:a |the |an )?"
    r"(?:train|bus|truck|car|jeep|traffic|mrt|lrt|tren|sasakyan|oncoming)\b".replace("{g}", _gap(2)),
    # researching a method
    r"\b(?:researching|searching|searched for|search for|looking up|looked up|googling|googled|reading about|looking for|look up) "
    r"(?:ways|methods|how) to (?:die|kill myself|end it|end my life|overdose|commit suicide|hang myself)\b",
    rf"\bhow (?:many|much) {_gap(2)}{_PILLS} {_gap(5)}(?:to die|die|to kill|kill me|kill myself|lethal|fatal|to overdose|overdose|od|"
    r"not wake up|never wake up|to end it|end it)\b",
    r"\b(?:lethal|fatal|deadly) (?:dose|amount|overdose)\b",
    r"\b(?:painless|peaceful)(?:est)? (?:way|ways|method|methods) to (?:die|go|end it|kill myself|commit suicide|suicide|end my life|not wake up)\b",
    r"\b(?:easiest|quickest|fastest|surest|best|least painful|quietest) (?:way|ways|method|methods) to "
    r"(?:die|end it|kill myself|commit suicide|suicide|end my life|not wake up|overdose)\b",
    r"\bhow (?:to|do (?:i|you)|can i|would i|should i) (?:tie a noose|make a noose|kill myself|commit suicide|end my life|"
    r"overdose|die painlessly|hang myself|slit my wrists)\b",
    # preparation: goodbye letters, letters to the people they love
    r"\b(?:wrote|written|write|writing|left|leaving|leave|finished|prepared|preparing|sent|recorded|recording) "
    r"(?:a |the |my |some |all |all the |all my )?(?:goodbye|farewell|last|final|suicide|parting) (?:letters?|notes?|messages?|texts?|videos?)\b",
    r"\b(?:wrote|written|writing|left|leaving|finished|prepared) (?:the |my |some |all |all the )?(?:letters|notes) (?:to|for) "
    r"(?:my |all my |every )?(?:family|everyone|everybody|parents|friends|mom|dad|mother|father|ma|pa|loved ones|kids|children|"
    r"wife|husband|partner|girlfriend|boyfriend|sister|brother|siblings|people|all of you|you all|them)\b",
    r"\b(?:wrote|written|writing|left|leaving|finished) (?:a |the |my )?(?:letter|note) (?:to|for) (?:my |all my )?"
    r"(?:family|everyone|everybody|loved ones|all of you|you all)\b",
    rf"\b(?:nagsulat|sumulat|sinulat|isinulat|nagiwan|nag iwan|iniwan|magiiwan|nagiiwan|mag iiwan) {_gap(3)}(?:sulat|liham|letter|note) "
    rf"{_gap(1)}(?:para sa|sa) (?:aking |mga |ang )?(?:pamilya|inyo|inyong lahat|lahat|kanila|magulang|mama|papa|nanay|tatay|mahal ko)\b",
    r"\b(?:huling|last) (?:sulat|liham)\b",
]
_METHOD_STANDALONE = [
    # First person + going to jump + a high place anywhere in the message.
    rf"\b(?:going to|will|ill|about to|gonna|mag) {_gap(2)}jump\b",
]
_PLAN_TIMELINE = (
    r"\b(?:tonight|tomorrow|this weekend|later|today|right now|soon|in an hour|"
    r"mamaya|mamayang gabi|bukas|ngayon|ngayong gabi|"
    r"about to|plan|planning|planned|decided|balak|ready|handa|"
    r"suicide note|my note|wrote (?:a|my) note|"
    r"goodbye|paalam|farewell|last (?:message|song|post|text|wish|words)|huling mensahe)\b"
)
_FAREWELL = [
    r"\bthis is (?:my )?goodbye\b",
    r"\b(?:goodbye|paalam|farewell|bye) {g}(?:everyone|everybody|all of you|inyong lahat|sa lahat|world|guys|forever)\b".replace("{g}", _gap(2)),
    r"\b(?:wont|will not|not going to|wouldnt|might not|may not|dont think ill|dont think i will|dont think id) (?:be )?"
    r"(?:here|around|alive) (?:much longer|for (?:much )?longer|for long|anymore|any more|tomorrow|by tomorrow|after tonight)\b",
    r"\blast time (?:youll|you will|you|anyone will|anybody will|anyone|anybody)(?: ever)? (?:hear from|see|talk to|hear) me\b",
    r"\b(?:paalam|nagpaalam|magpapaalam|mamamaalam) na (?:ako|ko) sa (?:inyong lahat|lahat|kanilang lahat|inyo|kanila)\b",
    r"\btell (?:my )?(?:mom|mum|dad|mother|father|mama|papa|ma|pa|family|parents|sister|brother|everyone|everybody|them|her|him|"
    r"wife|husband|kids|girlfriend|boyfriend|friends)(?: that)? (?:im sorry|i loved|goodbye|i was sorry|sorry)\b",
    rf"\bpakisabi (?:kay|sa) {_gap(2)}(?:na )?(?:sorry|patawad|paalam|mahal ko (?:siya|sila|kayo))\b",
    r"\b(?:hindi|di) na (?:ako|ko) (?:aabot|makakaabot|aabutan|abutin)(?: ng| sa| hanggang)? (?:bukas|umaga|next week|pasko|bagong taon)\b",
    r"\bmade (?:my )?peace with (?:dying|death|leaving this world|leaving)\b",
    r"\b(?:my|ang) (?:last|huling) (?:message|song|post|text|mensahe)\b",
    r"\bhuling mensahe\b",
    # "I left a note on the fridge" is not this; a suicide note is.
    r"\b(?:wrote|writing|written|left|leaving) (?:my|a|the) suicide note\b",
]
_DISTRESS = (
    r"\b(?:di ko na kaya|hindi ko na kaya|ayoko na|i cant|cant do this|im sorry|sorry|forgive me|patawad|"
    r"ready to go|its time|it is time|time to go|handa na ako|oras na|"
    r"salamat sa lahat|thank you for everything|thanks for everything)\b"
)

# Weak preparation cues: a check-in on their own, crisis next to "I'm done",
# distress or a goodbye ("i'm done. i've written the letters.").
_PREP_WEAK = [
    r"\b(?:wrote|written|finished|writing) (?:the|my|all the|all my) letters\b",
    r"\b(?:wrote|written|left|leaving) (?:a|my|the) (?:note|letter)(?= ?\||$)",
    r"\b(?:put|putting|got|getting|have|settled|settling) (?:all )?my affairs in order\b",
    r"\bmade (?:my )?peace with (?:it|it all|everything)\b",
    r"\bnagpaalam na (?:ako|ko) sa (?:mga )?(?:kaibigan|pamilya|magulang|mahal)\b",
]
_GIVING_AWAY = [
    rf"\b(?:giving|gave|give|given|getting rid of|got rid of) away {_gap(2)}(?:things|stuff|belongings|possessions|pets?|cat|dog|valuables|savings|everything)\b",
    r"\b(?:giving|gave|give|given) (?:away )?(?:all |most |some )?(?:of )?my (?:things|stuff|belongings|possessions|valuables|savings)\b",
    r"\b(?:giving|gave|give|given) my (?:pets?|cat|dog) (?:away|to)\b",
    rf"\b(?:ipamimigay|pinamigay|ipinamigay|pinapamigay|ipinapamigay|ipamigay|binigay|ibinigay|ibibigay) {_gap(4)}(?:gamit|pusa|aso|alaga|ipon)\b",
]
_NO_NEED = [
    rf"\b(?:wont|will not|wouldnt|dont)(?: be)? (?:need|needing) {_gap(2)}(?:anymore|any more|where im going)\b",
    r"\b(?:hindi|di) (?:ko|ko na|na ko) (?:na )?(?:kailangan|kakailanganin)\b",
]
_DONE = (
    r"\b(?:im|i am) (?:just )?(?:so )?(?:really )?done(?= ?\||$| with (?:everything|it all|all of this|this life|everyone|people|trying))"
    r"|\btapos na (?:ako|ko)(?= ?\||$)|\bayoko na(?= ?\||$)"
)


def _any(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns))


_COMPOSED_PATTERN = _any(_CRISIS_COMPOSED)
_METHOD_PATTERN = _any(_METHOD)
_JUMP_INTENT_PATTERN = _any(_METHOD_STANDALONE)
_HIGH_PLACE_PATTERN = re.compile(rf"\b{_HIGH_PLACE}\b")
_PLAN_PATTERN = re.compile(_PLAN_TIMELINE)
_FAREWELL_PATTERN = _any(_FAREWELL)
_DISTRESS_PATTERN = re.compile(_DISTRESS)
_LEGACY_FAREWELL_PATTERN = re.compile(r"\b(?:goodbye|paalam|bye|farewell)\b")
_PREP_WEAK_PATTERN = _any(_PREP_WEAK)
_GIVING_AWAY_PATTERN = _any(_GIVING_AWAY)
_NO_NEED_PATTERN = _any(_NO_NEED)
_NO_NEED_EN_PATTERN = re.compile(_NO_NEED[0])
_DONE_PATTERN = re.compile(_DONE)

# Second, gentler tier: hopelessness and exhaustion that is not explicit
# self-harm language. These still get music -- the user asked for it and nothing
# here says they are in danger -- but with a check-in and a way to reach a
# counselor. Kept separate from _CRISIS_PHRASES on purpose: a false positive
# here costs one banner, while promoting these to crisis would withhold music
# from every student who types "hindi ko na kaya" about a deadline.
_CONCERN_PHRASES = [
    # English
    r"(?:feel(?:ing)?|so|i'?m|i am) (?:completely |totally )?hopeless",
    r"(?:feel(?:ing)?|so|i'?m|i am) (?:completely |totally )?worthless",
    r"don'?t know what to do anymore",
    r"can'?t (?:take|handle|do) (?:it|this|anything) anymore",
    r"giv(?:e|ing) up on (?:everything|life|myself)",
    r"no (?:point|use) (?:in )?(?:anything|trying)",
    r"(?:nobody|no one) (?:cares|would care|would miss me)",
    r"tired of (?:everything|living|life|being alive)",
    r"(?:living|life) is (?:pointless|meaningless|non?e?sen[cs]e)",
    r"i'?m (?:just )?a burden",
    r"wish i (?:could )?(?:disappear|never woke up|was never born)",
    r"(?:empty|numb) inside",
    # Filipino / Taglish
    r"hindi ko na kaya",
    r"di ko na kaya",
    r"suko na ako",
    r"pagod na (?:pagod na )?ako sa (?:lahat|buhay)",
    r"wala (?:na )?akong silbi",
    r"walang (?:kwenta|silbi|saysay) (?:ang )?(?:buhay ko|ako)",
    r"walang (?:nagmamahal|nakakaintindi) sa akin",
    r"wala nang (?:pag-?asa|patutunguhan)",
]

_CONCERN_PATTERN = re.compile("|".join(_CONCERN_PHRASES), re.IGNORECASE)

# Ambiguous passive phrasing, matched on normalized text. Too unclear to take
# music away, too heavy to answer with music and nothing else.
_CONCERN_COMPOSED = [
    r"\b(?:whats|what is) (?:even )?(?:the )?point(?= ?\||$)",
    r"\b(?:whats|what is) (?:even )?(?:the )?point (?:anymore|of (?:anything|it all|trying|life|everything)|in (?:anything|trying|life))\b",
    r"\b(?:no|dont see (?:a|any|the)|cant see (?:a|any|the)) point (?:anymore|any more|in anything|of anything)\b",
    r"\bnothing (?:even |really )?matters(?: anymore)?\b",
    r"\bwalang (?:saysay|kwenta) (?:ang )?lahat\b",
    r"\bi give up(?= ?\||$)",
    r"\bcant go on(?= ?\||$)",
    r"\b(?:no|lost (?:my|the|all)) (?:motivation|energy|will|drive) to (?:keep going|continue|go on|do anything)\b",
    r"\bsleep forever\b|\bmatulog (?:na lang )?(?:ng )?(?:forever|habambuhay|panghabambuhay)\b",
    r"\b(?:want|wish) (?:to |i could )?(?:just )?(?:disappear|vanish|run away from everything)\b",
    r"\bpabigat (?:lang |na lang )?(?:ako|ko)\b",
    r"\b(?:a|such a) burden (?:to|on|for) (?:everyone|everybody|my family|them|my parents)\b",
    r"\bwala (?:na )?(?:akong|kong|ako ng) gana (?:sa )?(?:lahat|kahit ano|anything|everything)\b",
    r"\b(?:my )?life is (?:pointless|meaningless|useless|worthless|empty|a waste)\b",
    r"\b(?:finally|really) (?:going to|gonna) do it\b|\b(?:going to|will|ill) (?:finally )?do it (?:tonight|now|today|tomorrow)\b",
    r"\b(?:nobody|no one|noone) (?:will |would |is going to )?(?:even )?(?:care|cares|miss me|notice|remember me)(?= ?\||$| anyway)",
    r"\bwaste of (?:space|oxygen|air|life)\b",
    r"\b(?:the world|nobody|no one|everyone|they) (?:doesnt|dont|wont|does not|do not) need me\b",
    r"\bthinking (?:about|of) how (?:i|id|ill|i would|i will|to) (?:do it|end it|go)\b",
    r"\bi (?:just )?want out\b(?! of)",
    r"\bforget (?:that )?i (?:ever )?existed\b",
    r"\b(?:sumuko|suko na (?:ako|ko)) sa buhay\b",
    # Someone else at risk ("my friend wants to kill herself") is appended from
    # _SOMEONE_ELSE below: the concern tier, music plus the hotline list, which
    # the owner decided on 2026-10-06 must reach these users.
]

# Risk language about another person ("my friend wants to kill herself, what
# do I do"). It decides `support_subject`, i.e. which words the app shows; the
# tier still comes from the checks above, and this list also counts as concern.
_SOMEONE_ELSE = [
    r"\b(?:wants?|wanted|trying|tried|going|plans?|planning|thinking (?:about|of)) (?:to )?(?:[^\s|]+ )?"
    r"(?:kill|hurt|harm|cut|end) (?:herself|himself|themselves|her life|his life|their life|their own life)\b",
    r"\b(?:gusto|balak)(?: na)? (?:niyang|nyang|niya|nya|nilang) (?:na )?(?:mamatay|magpakamatay)\b",
    rf"\b(?:my|our|si|ang|yung|kaibigan ko|kapatid ko) {_gap(1)}(?:friend|best friend|bestfriend|bff|brother|sister|mom|"
    rf"mother|dad|father|cousin|classmate|roommate|girlfriend|boyfriend|partner|son|daughter|kaibigan|kapatid|kuya|"
    rf"ate|nanay|tatay|pinsan)\b {_gap(6)}(?:suicidal|suicide|kill (?:herself|himself|themselves)|self harm|cutting|"
    r"hurting (?:herself|himself|themselves)|magpakamatay|mamatay)\b",
]
_CONCERN_COMPOSED += _SOMEONE_ELSE
_CONCERN_COMPOSED_PATTERN = _any(_CONCERN_COMPOSED)
_SOMEONE_ELSE_PATTERN = _any(_SOMEONE_ELSE)

SUPPORT_SUBJECT_SELF = "self"
SUPPORT_SUBJECT_SOMEONE_ELSE = "someone_else"

# The model alone only raises a concern when it is confident: a low-confidence
# "depressing" is as likely to be a sad song request as a person in trouble.
_CONCERN_EMOTIONS = {"depressing"}
_CONCERN_CONFIDENCE_BANDS = {"high"}

SOMEONE_ELSE_CHECK_IN_MESSAGE = (
    "It sounds like you're worried about someone you care about. If they might be in "
    "danger right now, call emergency services and stay with them if you can. You don't "
    "have to handle this alone -- the people below can help you work out how to support "
    "them, and you deserve support too."
)

SOMEONE_ELSE_CRISIS_MESSAGE = (
    "It sounds like someone you care about may be in danger. If they might act on it "
    "soon, call your local emergency number now and stay with them if you can. A crisis "
    "line can also talk you through what to say and do -- you don't have to handle this "
    "alone, and what you're carrying matters too."
)

CONCERN_CHECK_IN_MESSAGE = (
    "It sounds like things have been really heavy lately. Music can help, but you "
    "don't have to carry this alone -- talking to a counselor or someone you trust "
    "can make a real difference."
)

CRISIS_SUPPORT_MESSAGE = (
    "It sounds like you might be going through something really heavy right now, "
    "and that matters more than a playlist. If you're in immediate danger, please "
    "contact your local emergency number right now. If you're having thoughts of "
    "suicide or self-harm, please reach out to a crisis line in your area, a mental "
    "health professional, or someone you trust -- a friend, family member, or "
    "counselor -- and let them know how you're feeling. You deserve support from a "
    "real person, not just music."
)


def assess_crisis_severity(text: str) -> str | None:
    """None, SEVERITY_CRISIS, or SEVERITY_IMMINENT (a plan, method or timeline).

    Tuned for recall: a false alarm costs one support screen, a miss could cost
    a life. Measure any change with `manage.py eval_crisis_detection`.
    """
    if not text:
        return None
    norm = normalize_for_safety(text)

    done_or_distress = bool(_DONE_PATTERN.search(norm) or _DISTRESS_PATTERN.search(norm))
    method = bool(_METHOD_PATTERN.search(norm)) or bool(
        _JUMP_INTENT_PATTERN.search(norm) and _HIGH_PLACE_PATTERN.search(norm)
    )
    # Preparation: weak cues only count next to "I'm done", distress or a goodbye,
    # and giving things away only next to "won't need it anymore".
    preparing = bool(
        _PREP_WEAK_PATTERN.search(norm)
        and (done_or_distress or _LEGACY_FAREWELL_PATTERN.search(norm))
    ) or bool(_GIVING_AWAY_PATTERN.search(norm) and _NO_NEED_PATTERN.search(norm))
    farewell = bool(_FAREWELL_PATTERN.search(norm)) or bool(
        _LEGACY_FAREWELL_PATTERN.search(norm) and done_or_distress
    )
    crisis = (
        method
        or preparing
        or farewell
        or bool(_CRISIS_PATTERN.search(text))
        or bool(_COMPOSED_PATTERN.search(norm))
    )
    if not crisis:
        return None
    if method or preparing or farewell or _PLAN_PATTERN.search(norm):
        return SEVERITY_IMMINENT
    return SEVERITY_CRISIS


def assess_crisis_risk(text: str) -> bool:
    """True if `text` reads as suicidal or self-harm risk (see assess_crisis_severity)."""
    return assess_crisis_severity(text) is not None


def assess_concern(text: str, result: dict | None = None) -> str | None:
    """Why `text` warrants a gentle check-in, or None.

    Returns "phrase" when the text itself sounds hopeless, "model" when the
    classifier is confident the emotion is depressing. Only meaningful for text
    that already passed `assess_crisis_risk`; crisis always takes precedence.
    """
    if text:
        norm = normalize_for_safety(text)
        if (
            _CONCERN_PATTERN.search(text)
            or _CONCERN_PATTERN.search(norm)
            or _CONCERN_COMPOSED_PATTERN.search(norm)
            # Preparation or "I'm done" on its own: unclear, so a check-in.
            or _PREP_WEAK_PATTERN.search(norm)
            or _GIVING_AWAY_PATTERN.search(norm)
            or _NO_NEED_EN_PATTERN.search(norm)
            or _DONE_PATTERN.search(norm)
        ):
            return "phrase"
    if isinstance(result, dict):
        emotion = str(result.get("emotion") or "").strip().lower()
        band = str(result.get("confidence_band") or "").strip().lower()
        if emotion in _CONCERN_EMOTIONS and band in _CONCERN_CONFIDENCE_BANDS:
            return "model"
    return None


# Who a clause is about. From a mention of another person ("my sister", "she")
# to the end of the clause is about them -- "my sister says she's going to jump
# off a bridge tonight" -- unless the user turns to themselves on the way
# ("my friend is suicidal and honestly I want to die too").
_OTHER_PERSON = re.compile(
    r"\b(?:(?:my|our|si|ni|kay|ang|yung|kaibigan ko|kapatid ko) (?:[^\s|]+ )?(?:friend|best friend|bestfriend|bff|"
    r"brother|sister|mom|mum|mother|dad|father|parent|cousin|classmate|roommate|girlfriend|boyfriend|bf|gf|"
    r"partner|son|daughter|kid|wife|husband|aunt|uncle|grandma|grandpa|coworker|officemate|groupmate|"
    r"kaibigan|kapatid|kuya|ate|nanay|tatay|mama|papa|pinsan|anak|asawa|tita|tito|lola|lolo|jowa)|"
    r"(?:kaibigan|kapatid|kuya|ate|nanay|tatay|mama|papa|pinsan|anak|asawa|tita|tito|lola|lolo|jowa) (?:ko|namin|natin)|"
    r"someone i know|a friend|(?:she|he|they|siya|sya|niya|niyang|nya|nyang|nila|nilang))\b"
)
_TURN_TO_SELF = re.compile(
    r"\b(?:and|but|so|also|tapos|pero|at)\b (?:[^\s|]+ ){0,2}(?:i|im|ive|id|ill|ako|me too|so am i)\b"
)
# "my friend told me to kill myself": the risk is still the user's.
_ABOUT_MYSELF = re.compile(r"\b(?:myself|sarili ko|my life|my own life)\b")


def _sounds_at_risk(norm: str) -> bool:
    return bool(
        _CRISIS_PATTERN.search(norm)
        or _COMPOSED_PATTERN.search(norm)
        or _METHOD_PATTERN.search(norm)
        or _FAREWELL_PATTERN.search(norm)
        or _CONCERN_PATTERN.search(norm)
        or _CONCERN_COMPOSED_PATTERN.search(norm)
    )


def support_subject(text: str) -> str:
    """Whether risk language in `text` is about the user or about someone else.

    Only wording depends on this; the tier comes from the checks above. It is
    "someone_else" when the risk sits in clauses about another person and
    nothing the user says about themselves sounds at risk.
    """
    if not text:
        return SUPPORT_SUBJECT_SELF
    norm = normalize_for_safety(text)
    if not (_OTHER_PERSON.search(norm) or _SOMEONE_ELSE_PATTERN.search(norm)):
        return SUPPORT_SUBJECT_SELF

    own_words = []
    for clause in norm.split("|"):
        mention = _OTHER_PERSON.search(clause)
        if not mention:
            own_words.append(clause)
            continue
        about_them = clause[mention.start():]
        if _ABOUT_MYSELF.search(about_them):
            own_words.append(clause)
            continue
        turn = _TURN_TO_SELF.search(about_them)
        own_words.append(clause[:mention.start()] + (about_them[turn.start():] if turn else ""))
    own_text = _SOMEONE_ELSE_PATTERN.sub(" | ", " | ".join(own_words))

    if _sounds_at_risk(own_text):
        return SUPPORT_SUBJECT_SELF
    if _sounds_at_risk(norm):
        return SUPPORT_SUBJECT_SOMEONE_ELSE
    return SUPPORT_SUBJECT_SELF


def build_crisis_support_message() -> str:
    """The safety message, with a region-specific hotline appended if configured.

    `CRISIS_HOTLINE_TEXT` is intentionally empty by default -- shipping a wrong or
    outdated crisis line is worse than shipping none. Set it in the environment
    (see .env.example) to a verified, current hotline for your deployment's region
    before relying on this in front of real users.
    """
    hotline = str(getattr(settings, "CRISIS_HOTLINE_TEXT", "") or "").strip()
    if hotline:
        return f"{CRISIS_SUPPORT_MESSAGE}\n\n{hotline}"
    return CRISIS_SUPPORT_MESSAGE
