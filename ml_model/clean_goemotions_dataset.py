"""
Clean GoEmotions (simplified) into EmoTune's 13-label schema for training.

GoEmotions is already scrubbed at the source -- no URLs or HTML, and personal
names are masked -- but it is Reddit comments labelled with 27 fine-grained
emotions, and several of those do not mean what their EmoTune counterpart
means. Everything this script drops, it drops for a reason measured on the
data itself:

* **Training uses its own label map, not `GOEMOTIONS_LABEL_MAP`.** That shared
  map scores the runtime GoEmotions fallback in `emotion_classifier.py`, where
  it aggregates model probabilities; changing it would change what live users
  get. For *training labels* it is too loose. Sampled single-label rows:

  - `love` (1,760 rows) is overwhelmingly about things -- "Love futurama.",
    "I loved that episode". Only 34 rows mention a partner. It becomes `happy`,
    and `romantic` only when AFFECTION_ROMANTIC_MARKERS matches.
  - `desire` is "I wish I could upvote this", `caring` is sympathy ("Stay
    safe!"), `approval` is agreement ("I strongly agree"), `disapproval` is
    disagreement, `remorse` is apologies ("Sorry for the spelling mistake"),
    `confusion` is questions, `embarrassment` is cringe, and `realization` is
    "I didn't know until a couple months ago". None of these is the EmoTune
    emotion they used to map to, so they are dropped. `desire` keeps the rows
    that are romantic by marker.

* **Rows whose labels map to two different EmoTune labels are dropped.** The
  old trainer took the first mapped label, so "joy;sadness" trained as happy.

* **Splits are deduplicated test-first.** A text seen in test is removed from
  validation and train, so duplicates cannot leak into evaluation. A text that
  appears with two different EmoTune labels is dropped everywhere.

* `[NAME]` is replaced with a real first name (seeded, so reruns match): users
  never type the literal token. `[RELIGION]` rows (121) are dropped rather than
  guessing a religion. Reddit `r/` and `u/` references are stripped.

Output is a `text,emotion,split` CSV, where split is GoEmotions' own
train/validation/test, plus a JSON report recording every drop.

Usage:
    python ml_model/clean_goemotions_dataset.py
"""
from __future__ import annotations

from _bootstrap import ensure_local_venv

ensure_local_venv()

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from datasets import load_dataset  # noqa: E402

from clean_text_emotion_dataset import (  # noqa: E402
    AFFECTION_ROMANTIC_MARKERS,
    MAX_WORDS,
    MIN_ALPHA_RATIO,
    MIN_WORDS,
    alpha_ratio,
    dedupe_key,
)
from ml.emotion_labels import EMOTIONS, call_huggingface_loader  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "dataset" / "goemotions.cleaned.csv"
DEFAULT_REPORT = REPO_ROOT / "ml_model" / "artifacts" / "goemotions_cleaning_report.json"

# GoEmotions label -> EmoTune label, for training only (see module docstring).
# `love` and `desire` are absent: they are split by content in map_label.
TRAINING_LABEL_MAP = {
    "joy": "happy",
    "amusement": "happy",
    "excitement": "happy",
    "gratitude": "happy",
    "admiration": "happy",
    "sadness": "sad",
    "grief": "sad",
    "disappointment": "sad",
    "anger": "angry",
    "annoyance": "angry",
    "disgust": "angry",
    "fear": "fear",
    "nervousness": "fear",
    "optimism": "motivational",
    "pride": "motivational",
    "relief": "calm",
    "surprise": "surprising",
}

# Measured as not meaning their old EmoTune label; a row carrying only these
# (or `neutral`) has nothing to teach.
DROPPED_SOURCE_LABELS = {
    "approval", "disapproval", "caring", "remorse",
    "confusion", "embarrassment", "realization", "curiosity", "neutral",
}

# Mixed English and Filipino names, matching who EmoTune is built for.
NAME_FILLERS = [
    "Alex", "Sam", "Jordan", "Maria", "Juan", "Angel", "Miguel", "Sarah",
    "John", "Paolo", "Bea", "Carlo", "Jess", "Mark", "Anna", "Kim",
]
NAME_SEED = 42
# Process order for dedupe: whatever survives in test stays out of train.
SPLIT_ORDER = ("test", "validation", "train")

NAME_RE = re.compile(r"\[NAME\]")
RELIGION_RE = re.compile(r"\[RELIGION\]")
REDDIT_REF_RE = re.compile(r"(?<!\w)/?\b[ru]/\w+")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(raw: str, rng: random.Random) -> str:
    text = REDDIT_REF_RE.sub(" ", str(raw or ""))
    text = NAME_RE.sub(lambda _: rng.choice(NAME_FILLERS), text)
    return WHITESPACE_RE.sub(" ", text).strip()


def map_label(source_label: str, text: str) -> str | None:
    if source_label in ("love", "desire"):
        if AFFECTION_ROMANTIC_MARKERS.search(text):
            return "romantic"
        return "happy" if source_label == "love" else None
    return TRAINING_LABEL_MAP.get(source_label)


def clean(dataset) -> tuple[list[tuple[str, str, str]], dict]:
    label_names = dataset["train"].features["labels"].feature.names
    rng = random.Random(NAME_SEED)
    counts = Counter()
    source_labels = Counter()
    candidates: list[tuple[str, str, str, str]] = []  # key, text, emotion, split

    for split in SPLIT_ORDER:
        for item in dataset[split]:
            counts["read"] += 1
            raw_labels = [label_names[i] for i in item["labels"]]
            source_labels.update(raw_labels)
            raw_text = str(item["text"] or "")

            if RELIGION_RE.search(raw_text):
                counts["dropped_religion_placeholder"] += 1
                continue

            text = normalize_text(raw_text, rng)
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

            mapped = {map_label(label, text) for label in raw_labels} - {None}
            if not mapped:
                if set(raw_labels) <= DROPPED_SOURCE_LABELS:
                    counts["dropped_unmapped_label"] += 1
                else:
                    counts["dropped_desire_not_romantic"] += 1
                continue
            if len(mapped) > 1:
                counts["dropped_ambiguous_multilabel"] += 1
                continue
            emotion = mapped.pop()
            if emotion not in EMOTIONS:
                counts["dropped_invalid_label"] += 1
                continue

            key = dedupe_key(text)
            if not key:
                counts["dropped_empty_after_normalize"] += 1
                continue
            candidates.append((key, text, emotion, split))

    labels_by_key: dict[str, set[str]] = {}
    for key, _, emotion, _ in candidates:
        labels_by_key.setdefault(key, set()).add(emotion)

    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for key, text, emotion, split in candidates:
        if len(labels_by_key[key]) > 1:
            counts["dropped_conflicting_label"] += 1
            continue
        if key in seen:
            counts["dropped_duplicate"] += 1
            continue
        seen.add(key)
        rows.append((text, emotion, split))
    counts["kept"] = len(rows)

    label_distribution = Counter(emotion for _, emotion, _ in rows)
    report = {
        "source_dataset": "go_emotions/simplified",
        "rows_read": counts["read"],
        "rows_kept": counts["kept"],
        "dropped": {
            key.removeprefix("dropped_"): value
            for key, value in sorted(counts.items())
            if key.startswith("dropped_")
        },
        "split_distribution": dict(Counter(split for _, _, split in rows)),
        "source_label_distribution": dict(source_labels.most_common()),
        "label_distribution": dict(label_distribution.most_common()),
        "labels_present": sorted(label_distribution),
        "labels_missing_from_schema": sorted(set(EMOTIONS) - set(label_distribution)),
    }
    return rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    try:
        dataset = call_huggingface_loader(load_dataset, "go_emotions", "simplified")
    except Exception as error:
        print(f"Could not load GoEmotions: {error}")
        return 1

    rows, report = clean(dataset)
    if not rows:
        print("Cleaning produced no rows.")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["text", "emotion", "split"])
        writer.writerows(rows)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Read    {report['rows_read']:,} rows from go_emotions/simplified")
    print(f"Kept    {report['rows_kept']:,} rows -> {args.output}")
    print("Dropped:")
    for reason, count in sorted(report["dropped"].items(), key=lambda item: -item[1]):
        print(f"    {count:7,}  {reason}")
    print("Label distribution:")
    for label, count in report["label_distribution"].items():
        print(f"    {count:7,}  {label}")
    print("Splits: " + ", ".join(f"{k}={v:,}" for k, v in report["split_distribution"].items()))
    if report["labels_missing_from_schema"]:
        print("Labels this dataset cannot teach: " + ", ".join(report["labels_missing_from_schema"]))
    print(f"Report  -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
