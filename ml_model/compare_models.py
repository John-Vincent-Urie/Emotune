"""
Compare two saved emotion models side by side on the same sentences.

Accuracy on the training holdout can look good while the model still misreads
how real people write, so promotion is judged by a person reading the
predictions: does each label fit what the sentence actually says? This script
puts the served model and a candidate next to each other on
`dataset/model_comparison_prompts.csv` -- hand-written sentences that appear in
no training file -- and writes a review sheet with an empty `better` column to
fill in (A, B, both, neither).

`suggested_emotion` in the prompts file is only a starting point for the
reviewer, not ground truth. Edit it, or add your own rows (ideally real things
users have typed), before judging.

This compares the raw BERT models only. The served app also has a keyword and
GoEmotions fallback and the crisis check in front of it; those are unchanged by
retraining, so they are left out to keep the comparison about the model.

Usage:
    python3 ml_model/compare_models.py
    python3 ml_model/compare_models.py --candidate backend/ml/models/<dir>
"""
from __future__ import annotations

from _bootstrap import ensure_local_venv

ensure_local_venv('torch')

import argparse  # noqa: E402
import csv  # noqa: E402
from pathlib import Path  # noqa: E402

import torch  # noqa: E402
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "backend" / "ml" / "models"
DEFAULT_SERVED = MODELS_DIR / "bert_emotion_model"
DEFAULT_CANDIDATE = MODELS_DIR / "bert_emotion_model_textemotion_20261004"
DEFAULT_PROMPTS = REPO_ROOT / "dataset" / "model_comparison_prompts.csv"
DEFAULT_OUTPUT = REPO_ROOT / "ml_model" / "artifacts" / "model_comparison_review.csv"
MAX_LENGTH = 128


def load(model_dir: Path):
    if not (model_dir / "config.json").exists():
        raise SystemExit(
            f"No finished model at {model_dir} (config.json missing). "
            "If it is still training, wait for train_bert.py to exit."
        )
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
    return tokenizer, model


@torch.no_grad()
def predict(tokenizer, model, texts: list[str]) -> list[tuple[str, float, str, float]]:
    """(top label, its probability, runner-up label, its probability) per text."""
    id2label = model.config.id2label
    results = []
    for start in range(0, len(texts), 16):
        batch = tokenizer(
            texts[start:start + 16],
            truncation=True,
            max_length=MAX_LENGTH,
            padding=True,
            return_tensors="pt",
        )
        probs = torch.softmax(model(**batch).logits, dim=-1)
        top = probs.topk(2, dim=-1)
        for values, indices in zip(top.values.tolist(), top.indices.tolist()):
            results.append((
                id2label[indices[0]], values[0],
                id2label[indices[1]], values[1],
            ))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--served", type=Path, default=DEFAULT_SERVED, help="Model A (default: the served model)")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE, help="Model B")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    with args.prompts.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if (row.get("text") or "").strip()]
    texts = [row["text"].strip() for row in rows]

    print(f"A = {args.served.name}\nB = {args.candidate.name}\n")
    preds_a = predict(*load(args.served), texts)
    preds_b = predict(*load(args.candidate), texts)

    fits_a = fits_b = 0
    review = []
    for row, text, a, b in zip(rows, texts, preds_a, preds_b):
        suggested = (row.get("suggested_emotion") or "").strip()
        fits_a += a[0] == suggested
        fits_b += b[0] == suggested
        review.append({
            "text": text,
            "suggested_emotion": suggested,
            "A_prediction": a[0],
            "A_confidence": f"{a[1]:.0%}",
            "A_runner_up": f"{a[2]} {a[3]:.0%}",
            "B_prediction": b[0],
            "B_confidence": f"{b[1]:.0%}",
            "B_runner_up": f"{b[2]} {b[3]:.0%}",
            "models_agree": "yes" if a[0] == b[0] else "NO",
            "better": "",
        })

    width = min(max(len(t) for t in texts), 60)
    print(f"{'text':<{width}}  {'suggested':<12} {'A':<18} {'B':<18}")
    print("-" * (width + 52))
    for item in review:
        flag = "" if item["models_agree"] == "yes" else "  <-- differ"
        text = item["text"] if len(item["text"]) <= width else item["text"][: width - 1] + "…"
        print(
            f"{text:<{width}}  {item['suggested_emotion']:<12} "
            f"{item['A_prediction'] + ' ' + item['A_confidence']:<18} "
            f"{item['B_prediction'] + ' ' + item['B_confidence']:<18}{flag}"
        )

    total = len(review)
    differ = sum(item["models_agree"] == "NO" for item in review)
    print(
        f"\nMatches the suggested emotion: A {fits_a}/{total}, B {fits_b}/{total}. "
        f"The models disagree on {differ} sentences -- those are the ones to read closely."
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review[0]))
        writer.writeheader()
        writer.writerows(review)
    print(f"Review sheet -> {args.output} (fill in the `better` column: A, B, both, neither)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
