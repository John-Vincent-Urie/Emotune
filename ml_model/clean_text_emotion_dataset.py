

"""
Clean the "Text Emotion Classification 150k" CSV into EmoTune's 13-label schema.

The raw file is two corpora concatenated under one header, and they are not of
equal quality. Everything this script drops, it drops for a reason that was
measured on the file itself:

* **HappyDB portion** (~93k rows: affection, achievement, enjoy_the_moment,
  bonding, nature, exercise). Real human-written "happy moment" entries. These
  are the good half. Their labels are *topics* of a happy moment rather than
  emotions, so they are mapped by topic -- achievement/exercise read as
  motivational, nature as calm, and so on.

* **`sadness` (45,898 rows) is template-generated and is dropped entirely.**
  Measured: only 24,690 of the 45,898 are unique, the mean length is 5.3 words,
  and 60 sentence-final words cover 57% of the class, each landing 430-600 times
  ("sorrow" 598, "misery" 453, "depression" 449, "anguish" 449). Real writing
  does not distribute like that. The rows read as slot-filled frames -- "Biking
  pedals through somber.", "Museums remind me of barren.", "My spirit pulses
  with unhappy." The ~1.5k rows in the class that are *not* templates are
  mislabelled tweets ("Anybody know a good place to book a show in #Montreal",
  "#AutumnalEquinox the nights are drawing in"), so there is no clean subset
  worth rescuing. Training on this class would teach the model that "sad" means
  broken grammar. `--keep-sadness` overrides this, but the report will show what
  you are buying.

* **671 rows are misaligned.** `original_text` and `cleaned_text` hold entirely
  different texts (one a tweet, the other a HappyDB entry), which means the two
  source files were merged row-wise incorrectly. When the columns disagree we
  cannot tell which text the label belongs to, so the row is dropped.

* The small tweet-derived classes (joy, anger, fear, love, surprise) are kept
  but stripped of URLs and @handles. They are noisy and some rows are plainly
  mislabelled; they survive because they are the only negative-valence and
  surprise signal left once `sadness` is gone, and the training stage caps every
  class anyway.

Output is a two-column `text,emotion` CSV -- the same shape the other EmoTune
datasets use, so `data_pipeline.clean_dataset` can consume it unchanged -- plus
a JSON report recording every drop.

Usage:
    python ml_model/clean_text_emotion_dataset.py
    python ml_model/clean_text_emotion_dataset.py --keep-sadness
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ml.emotion_labels import EMOTIONS  # noqa: E402

DEFAULT_SOURCE = REPO_ROOT / "dataset" / "Text Emotion Classification 150k Dataset.csv"
DEFAULT_OUTPUT = REPO_ROOT / "dataset" / "text_emotion_classification.cleaned.csv"
DEFAULT_REPORT = REPO_ROOT / "ml_model" / "artifacts" / "text_emotion_cleaning_report.json"

# Source category -> EmoTune label. `affection` is deliberately absent: it is
# split by content, see AFFECTION_ROMANTIC_MARKERS.
CATEGORY_MAP = {
    # HappyDB topics. All of these are happy moments; the topic decides which
    # flavour of positive EmoTune label fits best.
    "achievement": "motivational",
    "exercise": "motivational",
    "enjoy_the_moment": "happy",
    "bonding": "happy",
    "nature": "calm",
    # Tweet/emotion-corpus labels.
    "joy": "happy",
    "anger": "angry",
    "fear": "fear",
    "love": "romantic",
    "surprise": "surprising",
}

# HappyDB's `affection` covers both partners and family ("Goodbye kisses from my
# children", "My fiance actually listened to what I had to say"). Only the
# partner half is `romantic` in EmoTune's schema; the rest is ordinary warmth,
# which is `happy`. Mapping the whole class to `romantic` would flood that label
# with family content.
AFFECTION_ROMANTIC_MARKERS = re.compile(
    r"\b("
    r"boyfriend|girlfriend|husband|wife|fiance|fiancee|spouse|partner|"
    r"anniversary|valentine|honeymoon|romantic|"
    r"my love|my darling|my sweetheart|"
    r"date night|first date|proposed|engaged|marry|married|wedding|"
    r"kiss|kissed|kissing|cuddle|cuddled|cuddling|snuggle|snuggled"
    r")\b",
    re.IGNORECASE,
)

DROPPED_CATEGORIES = {"sadness"}

# This source only ever produces `calm` (from `nature`) and `surprising` (from
# `surprise`, 66 rows) among these four -- `nostalgic` and `lonely` have no
# source category here at all. Excluded because those two mapped classes are
# too thin/off-topic to be worth keeping from this corpus. `happy` is also
# excluded -- it's this source's largest class by far and floods the combined
# training set relative to every other label.
EXCLUDED_LABELS = {"nostalgic", "surprising", "lonely", "calm", "happy"}

# With `happy` gone, `motivational` (achievement + exercise) is ~70% of what is
# left and swamps romantic/fear/angry. Keep at most this many rows of it, chosen
# at random; the fixed seed keeps the output reproducible across runs.
DOWNSAMPLE_LABELS = {"motivational": 5000}
DOWNSAMPLE_SEED = 42

URL_RE = re.compile(r"https?://\S+|www\.\S+|\ba\s+href\s+http\S*", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#(\w+)")
# U+FFFD plus the mojibake the source file already contains in place of emoji.
REPLACEMENT_RE = re.compile(r"[�]+")
WHITESPACE_RE = re.compile(r"\s+")
ALPHA_RE = re.compile(r"[a-z]")

MIN_WORDS = 3
MAX_WORDS = 60
MIN_ALPHA_RATIO = 0.6
# Below this word-overlap the two text columns are describing different events,
# so the row is a merge artefact rather than a typo fix.
MIN_COLUMN_AGREEMENT = 0.5


def normalize_text(raw: str) -> str:
    """Strip tweet furniture and whitespace noise without altering wording."""
    text = html.unescape(str(raw or ""))
    text = text.replace("\\n", " ").replace("\\t", " ")
    text = URL_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    # Keep the word, drop the '#': "#sad" carries the same signal as "sad".
    text = HASHTAG_RE.sub(r"\1", text)
    text = REPLACEMENT_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text.strip(" -–—:;,.")


def dedupe_key(text: str) -> str:
    return WHITESPACE_RE.sub(" ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def column_agreement(left: str, right: str) -> float:
    left_words = set(left.lower().split())
    right_words = set(right.lower().split())
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def alpha_ratio(text: str) -> float:
    stripped = text.replace(" ", "")
    if not stripped:
        return 0.0
    return len(ALPHA_RE.findall(text.lower())) / len(stripped)


def map_category(category: str, text: str) -> str | None:
    if category == "affection":
        return "romantic" if AFFECTION_ROMANTIC_MARKERS.search(text) else "happy"
    return CATEGORY_MAP.get(category)


def clean(source: Path, *, keep_sadness: bool) -> tuple[list[tuple[str, str]], dict]:
    dropped_categories = set() if keep_sadness else DROPPED_CATEGORIES

    counts = Counter()
    source_categories = Counter()
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()

    with source.open(encoding="utf-8", errors="replace", newline="") as handle:
        for record in csv.DictReader(handle):
            counts["read"] += 1

            category = str(record.get("category") or "").strip().lower()
            original = str(record.get("original_text") or "").strip()
            alternate = str(record.get("cleaned_text") or "").strip()
            source_categories[category or "<empty>"] += 1

            if not category:
                counts["dropped_empty_category"] += 1
                continue
            if not original and not alternate:
                counts["dropped_empty_text"] += 1
                continue

            # `cleaned_text` is the better column where it exists -- it fixes
            # typos the raw text has ("youare" -> "you're", "annd" -> "and").
            # It is only trustworthy when it is describing the same event.
            if original and alternate and original != alternate:
                if column_agreement(original, alternate) < MIN_COLUMN_AGREEMENT:
                    counts["dropped_misaligned_columns"] += 1
                    continue
            text = alternate or original

            if category in dropped_categories:
                counts["dropped_synthetic_category"] += 1
                continue

            text = normalize_text(text)
            if not text:
                counts["dropped_empty_after_normalize"] += 1
                continue

            word_count = len(text.split())
            if word_count < MIN_WORDS:
                counts["dropped_too_short"] += 1
                continue
            if word_count > MAX_WORDS:
                counts["dropped_too_long"] += 1
                continue
            if alpha_ratio(text) < MIN_ALPHA_RATIO:
                counts["dropped_low_alpha"] += 1
                continue

            emotion = map_category(category, text)
            if emotion is None:
                counts["dropped_unmapped_category"] += 1
                continue
            if emotion not in EMOTIONS:
                counts["dropped_invalid_label"] += 1
                continue
            if emotion in EXCLUDED_LABELS:
                counts["dropped_excluded_label"] += 1
                continue

            key = dedupe_key(text)
            if not key or key in seen:
                counts["dropped_duplicate"] += 1
                continue
            seen.add(key)

            rows.append((text, emotion))

    rng = random.Random(DOWNSAMPLE_SEED)
    for label, keep in DOWNSAMPLE_LABELS.items():
        indices = [i for i, (_, emotion) in enumerate(rows) if emotion == label]
        dropped = set(rng.sample(indices, max(len(indices) - keep, 0)))
        counts[f"dropped_downsampled_{label}"] += len(dropped)
        rows = [row for i, row in enumerate(rows) if i not in dropped]
    counts["kept"] = len(rows)

    label_distribution = Counter(emotion for _, emotion in rows)
    report = {
        "source_file": source.name,
        "rows_read": counts["read"],
        "rows_kept": counts["kept"],
        "keep_sadness": keep_sadness,
        "dropped": {
            key.removeprefix("dropped_"): value
            for key, value in sorted(counts.items())
            if key.startswith("dropped_")
        },
        "source_category_distribution": dict(source_categories.most_common()),
        "label_distribution": dict(label_distribution.most_common()),
        "labels_present": sorted(label_distribution),
        "labels_missing_from_schema": sorted(set(EMOTIONS) - set(label_distribution)),
    }
    return rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--keep-sadness",
        action="store_true",
        help="Keep the template-generated `sadness` class (see module docstring).",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source dataset not found: {args.source}")
        return 1

    rows, report = clean(args.source, keep_sadness=args.keep_sadness)
    if not rows:
        print("Cleaning produced no rows.")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["text", "emotion"])
        writer.writerows(rows)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Read    {report['rows_read']:,} rows from {args.source.name}")
    print(f"Kept    {report['rows_kept']:,} rows -> {args.output}")
    print("Dropped:")
    for reason, count in sorted(report["dropped"].items(), key=lambda item: -item[1]):
        print(f"    {count:7,}  {reason}")
    print("Label distribution:")
    for label, count in report["label_distribution"].items():
        print(f"    {count:7,}  {label}")
    if report["labels_missing_from_schema"]:
        print("Labels this dataset cannot teach: " + ", ".join(report["labels_missing_from_schema"]))
    print(f"Report  -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
