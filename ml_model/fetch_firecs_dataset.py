"""
Fetch FiReCS (Filipino-English Reviews with Code-Switching) and save it locally.

FiReCS is a real, natural Taglish corpus -- 10,487 Lazada product/service
reviews, hand-labelled by three native Filipino speakers, CC-BY-4.0, from
Ateneo de Manila University (Cosme & De Leon). See
https://huggingface.co/datasets/ccosme/FiReCS.

It does **not** go into `dataset/emotune_combined.csv` or get an `emotion`
column, for two reasons that are both about label validity rather than
formatting:

1. **Domain mismatch.** FiReCS rows are product/service reviews ("disappointed
   kasi di gumana ang dalawa", "super ganda... good quality po"). EmoTune's
   13 labels describe how the *speaker* feels right now, elicited by a mood
   prompt. A five-star review is not the same speech act as "I feel happy" --
   satisfaction with a product is not the same signal as the discrete moods
   EmoTune classifies, even when the words overlap.

2. **Label granularity mismatch.** FiReCS has 3 sentiment classes
   (negative/neutral/positive). EmoTune has 13 emotion classes. Collapsing
   "positive" onto one of {happy, motivational, calm, romantic, surprising,
   nostalgic} (all plausible, all different) is a guess this script refuses to
   make silently -- that guess would sit in the same file that also gates
   `backend/api/safety.py`'s crisis phrases, i.e. a real person in a bad moment
   could be on the other end of a wrong label here.

What this script gives you instead: a clean local `text,sentiment,split` CSV,
so the corpus is available offline for the things it's actually good for --
a natural-Taglish read for anyone hand-relabelling a sample onto the 13-label
schema, an evaluation set for whether the tokenizer/model handle code-switched
grammar at all, or a future auxiliary sentiment task. `--sample-for-review N`
prints N random rows per sentiment class so a human can start that relabelling
pass without re-downloading anything.

Usage:
    python ml_model/fetch_firecs_dataset.py
    python ml_model/fetch_firecs_dataset.py --sample-for-review 15
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_local_venv  # noqa: E402

ensure_local_venv(probe_module='datasets')

DATASET_DIR = REPO_ROOT / "dataset"
DEFAULT_OUTPUT = DATASET_DIR / "firecs_taglish_reviews.csv"
DEFAULT_REPORT = REPO_ROOT / "ml_model" / "artifacts" / "firecs_report.json"

# FiReCS encodes sentiment as a float: 0=negative, 1=neutral, 2=positive.
SENTIMENT_LABELS = {0.0: "negative", 1.0: "neutral", 2.0: "positive"}


def fetch_rows():
    from datasets import load_dataset

    dataset = load_dataset("ccosme/FiReCS")
    rows = []
    for split_name in ("train", "test"):
        for item in dataset[split_name]:
            text = str(item.get("review") or "").strip()
            if not text:
                continue
            sentiment = SENTIMENT_LABELS.get(item.get("label"))
            if sentiment is None:
                continue
            rows.append({"text": text, "sentiment": sentiment, "split": split_name})
    return rows


def write_csv(rows, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "sentiment", "split"])
        writer.writeheader()
        writer.writerows(rows)


def build_report(rows) -> dict:
    counts_by_split: dict[str, dict[str, int]] = {}
    for row in rows:
        split_counts = counts_by_split.setdefault(row["split"], {})
        split_counts[row["sentiment"]] = split_counts.get(row["sentiment"], 0) + 1
    return {
        "source": "https://huggingface.co/datasets/ccosme/FiReCS",
        "license": "CC-BY-4.0",
        "total_rows": len(rows),
        "counts_by_split": counts_by_split,
        "schema": "text,sentiment,split -- NOT EmoTune's text,emotion schema",
        "not_merged_into_emotune_combined_csv_because": [
            "Domain: Lazada product/service reviews, not mood/feeling statements.",
            "Granularity: 3-class sentiment, not EmoTune's 13-class emotion.",
            "A silent sentiment->emotion mapping would inject unvalidated "
            "labels into the data that also underpins crisis-safety behavior.",
        ],
    }


def print_review_sample(rows, per_class: int, seed: int = 13) -> None:
    rng = random.Random(seed)
    by_sentiment: dict[str, list[dict]] = {}
    for row in rows:
        by_sentiment.setdefault(row["sentiment"], []).append(row)

    for sentiment in ("negative", "neutral", "positive"):
        candidates = by_sentiment.get(sentiment, [])
        sample = rng.sample(candidates, min(per_class, len(candidates)))
        print(f"\n=== {sentiment} ({len(candidates)} rows total) ===")
        for row in sample:
            print(f"  {row['text'][:160]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--sample-for-review",
        type=int,
        default=0,
        metavar="N",
        help="Print N random rows per sentiment class, for a human doing a "
        "manual sentiment->emotion relabelling pass.",
    )
    args = parser.parse_args()

    print("Fetching ccosme/FiReCS from Hugging Face...")
    rows = fetch_rows()
    print(f"Fetched {len(rows)} rows.")

    write_csv(rows, args.output)
    print(f"Wrote {args.output.relative_to(REPO_ROOT)}")

    report = build_report(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {args.report.relative_to(REPO_ROOT)}")

    for split, counts in report["counts_by_split"].items():
        print(f"  {split}: {counts}")

    if args.sample_for_review:
        print_review_sample(rows, args.sample_for_review)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
