"""
Build the combined EmoTune final-stage dataset from every labelled source.

The final fine-tune stage is the only one that covers all 13 EmoTune labels, so
it decides what the deployed model can actually predict. It was pointed at
`emotune_custom_dataset.csv`, which is the weakest of the three sources
available:

    emotune_custom_dataset.csv   1,100 rows -> 164 unique  (936 duplicates, 85%)
    emotune_dataset_1200.csv     1,200 rows -> 1,200 unique (no duplicates)
    surveyed_datasets.csv           41 rows -> real survey responses

On its own the custom file leaves ~12 examples per label and a 13-row holdout
test set, which is too small to fine-tune on or to measure. The 1,200-row file
is clean and balanced but has no `mixed` examples at all, so it cannot replace
the custom file either -- `mixed` would become unpredictable.

Combining them is what actually works: the 1,200 file supplies ~100 rows for 12
labels, and the custom file and the survey supply the `mixed` examples plus
extra coverage everywhere else. Duplicates are removed across the union, so the
near-identical rows the sources share (they differ only in punctuation) collapse
to one.

`surveyed_datasets.csv` uses its own label names (`motivated`, `depressed`,
`surprise`, `stress`); those are mapped onto the canonical schema here rather
than silently dropped as invalid labels.

Usage:
    python ml_model/build_emotune_training_set.py
    EMOTUNE_DATASET_PATH=dataset/emotune_combined.csv python ml_model/train_bert.py
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
DEFAULT_OUTPUT = DATASET_DIR / "emotune_combined.csv"
DEFAULT_REPORT = REPO_ROOT / "ml_model" / "artifacts" / "emotune_combined_report.json"

# Ordered: earlier sources win a duplicate, so the largest clean source leads.
SOURCES = (
    ("emotune_dataset_1200.csv", True),
    ("emotune_custom_dataset.csv", True),
    ("surveyed_datasets.csv", False),
)

# surveyed_datasets.csv predates the canonical label names.
LABEL_ALIASES = {
    "motivated": "motivational",
    "depressed": "depressing",
    "surprise": "surprising",
    "stress": "stressed",
    "neutral": "calm",
}

WHITESPACE_RE = re.compile(r"\s+")


def canonical_label(raw: str) -> str | None:
    label = str(raw or "").strip().lower()
    label = LABEL_ALIASES.get(label, label)
    return label if label in EMOTIONS else None


def dedupe_key(text: str) -> str:
    return WHITESPACE_RE.sub(" ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def read_source(path: Path, has_header: bool) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        if has_header:
            next(reader, None)
        for record in reader:
            if len(record) < 2:
                continue
            text = WHITESPACE_RE.sub(" ", str(record[0] or "")).strip()
            label = canonical_label(record[1])
            if text and label:
                rows.append((text, label))
    return rows


def build() -> tuple[list[tuple[str, str]], dict]:
    combined: list[tuple[str, str]] = []
    seen: set[str] = set()
    per_source: dict[str, dict] = {}

    for filename, has_header in SOURCES:
        path = DATASET_DIR / filename
        if not path.exists():
            per_source[filename] = {"status": "missing"}
            continue

        rows = read_source(path, has_header)
        kept = 0
        for text, label in rows:
            key = dedupe_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            combined.append((text, label))
            kept += 1

        per_source[filename] = {
            "status": "ok",
            "rows_read": len(rows),
            "rows_contributed": kept,
            "duplicates_dropped": len(rows) - kept,
        }

    distribution = Counter(label for _, label in combined)
    report = {
        "output_rows": len(combined),
        "sources": per_source,
        "label_distribution": dict(sorted(distribution.items(), key=lambda item: -item[1])),
        "labels_missing": sorted(set(EMOTIONS) - set(distribution)),
    }
    return combined, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    combined, report = build()
    if not combined:
        print("No rows produced -- check that dataset/ still holds the source CSVs.")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["text", "emotion"])
        writer.writerows(combined)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for filename, stats in report["sources"].items():
        if stats.get("status") != "ok":
            print(f"{filename:32s} {stats.get('status')}")
            continue
        print(
            f"{filename:32s} read {stats['rows_read']:5d}  "
            f"contributed {stats['rows_contributed']:5d}  "
            f"duplicate {stats['duplicates_dropped']:5d}"
        )
    print(f"\nWrote {report['output_rows']:,} rows -> {args.output}")
    print("Label distribution:")
    for label, count in report["label_distribution"].items():
        print(f"    {count:5d}  {label}")
    if report["labels_missing"]:
        print("MISSING labels: " + ", ".join(report["labels_missing"]))
    print(f"Report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
