"""
Clean the three template-generated EmoTune files into the 13-label schema.

    dataset/emotune_anger_1000.csv        anger      -> angry
    dataset/emotune_depression_1000.csv   depression -> depressing
    dataset/stress.csv                    stress     -> stressed

They were screened before any rule below was written. They are free of the usual
dirt -- no nulls, no duplicates (1,000 unique texts each), no HTML or URLs, no
stray whitespace, no overlap with each other or with any other EmoTune dataset --
so the defects left are mechanical, and each is repaired or dropped for a reason
measured on the files themselves:

* **Labels are not schema labels.** `anger`/`depression`/`stress` would be
  rejected by `data_pipeline.clean_dataset` as invalid, so they are mapped.

* **A lowercase pronoun in 818 of the 1,000 depression rows** ("..., and i feel").
  The generator capitalised the first clause and not the second. This has no
  effect on the current model (`bert-base-uncased` lowercases everything), so it
  is cosmetic, but a file that is wrong as text would mislead a cased model, a
  keyword matcher, or whoever reads the manual-review samples. Repaired.

* **Plural topics with singular verbs.** The generator slots `assignments`,
  `exams` and `school requirements` into frames written for singular nouns
  ("assignments is difficult", "exams keeps failing during testing"): 231 rows
  across anger and stress. Repaired by conjugating the first verb after the
  topic, and nothing else -- "...assignments is difficult and my group is not
  finished yet" correctly keeps its second `is`.

* **"I'm tired of <topic> <verb phrase>" (58 anger rows)** is not a sentence
  ("I'm tired of debugging keeps crashing"). The frame is broken in every row it
  appears in, so dropping would erase it from the file. Inserting "how" makes all
  of them grammatical with a single word and without changing the meaning.

The BOM and the `id` column are dropped; the output is `text,emotion`, the shape
`data_pipeline.clean_dataset` and the other `*.cleaned.csv` files use. The source
files are not modified.

What this script cannot fix, and the report records so it is not forgotten: these
are slot-filled frames, not human writing (see `template_concentration`), so a
model trained on them learns the frames. Anger and stress are all about the same 24
student-project topics and depression is about none, so topic words can stand in
for the label.

Usage:
    python ml_model/clean_emotune_synthetic_datasets.py
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ml.emotion_labels import EMOTIONS  # noqa: E402

DATASET_DIR = REPO_ROOT / "dataset"
DEFAULT_REPORT = REPO_ROOT / "ml_model" / "artifacts" / "emotune_synthetic_cleaning_report.json"

# source file -> (label the file is expected to hold, EmoTune label)
SOURCES = {
    "emotune_anger_1000.csv": ("anger", "angry"),
    "emotune_depression_1000.csv": ("depression", "depressing"),
    "stress.csv": ("stress", "stressed"),
}

WHITESPACE_RE = re.compile(r"\s+")
# A standalone `i`, with or without a contraction ("i", "i'm", "i've"); not "i.e.".
LOWERCASE_I_RE = re.compile(r"(?<![\w.])i(?![\w.])")

PLURAL_TOPIC_VERB_RE = re.compile(
    r"\b(assignments|exams|school requirements) (is|keeps|has|was|doesn't|isn't)\b",
    re.IGNORECASE,
)
PLURAL_VERBS = {
    "is": "are",
    "keeps": "keep",
    "has": "have",
    "was": "were",
    "doesn't": "don't",
    "isn't": "aren't",
}
# "...exams was working yesterday but is broken today": the generator's second verb.
PLURAL_SECOND_VERB_RE = re.compile(r"\b(were working yesterday but) is\b")

# "tired of" followed by a bare topic (1-3 words) and a finite verb. Runs after
# the plural repair, so the plural forms (are/keep/have/were) must match too.
TIRED_OF_CLAUSE_RE = re.compile(
    r"\b(tired of) (?=(?:\w+ ){1,3}?(?:is|are|keeps?|was|were|has|have|suddenly)\b)",
    re.IGNORECASE,
)


def normalize_text(raw: str) -> str:
    return WHITESPACE_RE.sub(" ", str(raw or "")).strip()


def dedupe_key(text: str) -> str:
    return WHITESPACE_RE.sub(" ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def fix_lowercase_i(text: str) -> str:
    return LOWERCASE_I_RE.sub("I", text)


def fix_plural_agreement(text: str) -> str:
    def conjugate(match: re.Match) -> str:
        verb = match.group(2)
        return f"{match.group(1)} {PLURAL_VERBS[verb.lower()]}"

    fixed = PLURAL_TOPIC_VERB_RE.sub(conjugate, text)
    if fixed == text:
        return text
    return PLURAL_SECOND_VERB_RE.sub(r"\1 are", fixed)


def fix_tired_of_clause(text: str) -> str:
    return TIRED_OF_CLAUSE_RE.sub(r"\1 how ", text)


# (report key, repair). Applied in order; a row counts once per repair that changed it.
REPAIRS = (
    ("lowercase_i", fix_lowercase_i),
    ("plural_agreement", fix_plural_agreement),
    ("tired_of_clause", fix_tired_of_clause),
)


def template_concentration(texts: list[str]) -> dict:
    """How few distinct frames the file is built from -- not a defect we can fix."""
    openers = Counter(" ".join(text.lower().split()[:3]) for text in texts)
    closers = Counter(" ".join(re.sub(r"[.!?]$", "", text.lower()).split()[-3:]) for text in texts)
    return {
        "distinct_openers_first_3_words": len(openers),
        "distinct_closers_last_3_words": len(closers),
        "most_common_opener": openers.most_common(1)[0],
        "most_common_closer": closers.most_common(1)[0],
    }


def clean_file(source: Path, expected_label: str, emotion: str, seen: set[str]) -> tuple[list[tuple[str, str]], dict]:
    counts: Counter = Counter()
    rows: list[tuple[str, str]] = []

    with source.open(encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            counts["read"] += 1

            if str(record.get("emotion") or "").strip().lower() != expected_label:
                counts["dropped_unexpected_label"] += 1
                continue

            text = normalize_text(record.get("text"))
            if not text:
                counts["dropped_empty_text"] += 1
                continue

            for key, repair in REPAIRS:
                repaired = repair(text)
                if repaired != text:
                    counts[f"repaired_{key}"] += 1
                    text = repaired

            key = dedupe_key(text)
            if key in seen:
                counts["dropped_duplicate"] += 1
                continue
            seen.add(key)

            rows.append((text, emotion))

    counts["kept"] = len(rows)
    report = {
        "source_label": expected_label,
        "emotion": emotion,
        "rows_read": counts["read"],
        "rows_kept": counts["kept"],
        "dropped": {
            key.removeprefix("dropped_"): value
            for key, value in sorted(counts.items())
            if key.startswith("dropped_")
        },
        "repaired": {
            key.removeprefix("repaired_"): value
            for key, value in sorted(counts.items())
            if key.startswith("repaired_")
        },
        "template_concentration": template_concentration([text for text, _ in rows]),
    }
    return rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    missing = [name for name in SOURCES if not (args.source_dir / name).exists()]
    if missing:
        print("Source dataset(s) not found: " + ", ".join(str(args.source_dir / name) for name in missing))
        return 1

    for _, emotion in SOURCES.values():
        if emotion not in EMOTIONS:
            print(f"{emotion!r} is not in the EmoTune schema: {EMOTIONS}")
            return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    report: dict = {"files": {}}
    for name, (expected_label, emotion) in SOURCES.items():
        source = args.source_dir / name
        rows, file_report = clean_file(source, expected_label, emotion, seen)
        if not rows:
            print(f"Cleaning {name} produced no rows.")
            return 1

        output = args.output_dir / f"{source.stem}.cleaned.csv"
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["text", "emotion"])
            writer.writerows(rows)

        report["files"][name] = {**file_report, "output_file": output.name}
        print(f"{name}: read {file_report['rows_read']:,}, kept {file_report['rows_kept']:,} -> {output}")
        for reason, count in file_report["dropped"].items():
            print(f"    dropped   {count:5,}  {reason}")
        for reason, count in file_report["repaired"].items():
            print(f"    repaired  {count:5,}  {reason}")

    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report  -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
