#!/usr/bin/env python3
"""
Taglish domain adaptation: continued masked-LM training on FiReCS text.

FiReCS (`dataset/firecs_taglish_reviews.csv`, see `fetch_firecs_dataset.py`)
is real code-switched Filipino-English, but its labels are 3-class product
sentiment, not EmoTune's 13 emotions. This script uses the *text only* --
the sentiment column is never read -- so no guessed emotion labels reach the
data behind the classifier (and, through it, the crisis-safety path).

What it does:
1. Loads the encoder of a sequence-classification checkpoint (by default the
   completed Text-Emotion-150k stage-1 checkpoint), and borrows the MLM head
   from `bert-base-uncased` -- the checkpoint was fine-tuned from it, so the
   vocabulary and hidden size line up and the head is already trained.
2. Continues MLM training on the FiReCS *train* split; reports masked-LM
   perplexity on the FiReCS *test* split before and after, so it is visible
   whether the model actually got better at Taglish.
3. Writes the adapted encoder back into a copy of the original classifier
   (classification head kept), ready for `train_bert.py` via
   `EMOTUNE_MODEL_NAME=<output dir>` with the outside-corpus stages disabled.

Usage:
    python ml_model/adapt_taglish_mlm.py
    TAGLISH_MLM_RESUME=true python ml_model/adapt_taglish_mlm.py   # after a kill
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_local_venv  # noqa: E402

ensure_local_venv('torch')

import pandas as pd  # noqa: E402
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    BertForMaskedLM,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)
from transformers.trainer_utils import get_last_checkpoint

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "backend" / "ml" / "models"

SOURCE_MODEL = Path(os.getenv("TAGLISH_MLM_SOURCE", MODELS_DIR / "stage1_ckpt304.fallback"))
MLM_HEAD_MODEL = os.getenv("TAGLISH_MLM_HEAD_MODEL", "bert-base-uncased")
DATASET = Path(os.getenv("TAGLISH_MLM_DATASET", REPO_ROOT / "dataset" / "firecs_taglish_reviews.csv"))
OUTPUT_DIR = Path(os.getenv("TAGLISH_MLM_OUTPUT", MODELS_DIR / "stage1_taglish_mlm"))
WORK_DIR = OUTPUT_DIR.parent / f"{OUTPUT_DIR.name}.work"

MAX_LENGTH = int(os.getenv("TAGLISH_MLM_MAX_LENGTH", 96))
BATCH_SIZE = int(os.getenv("TAGLISH_MLM_BATCH_SIZE", 16))
EPOCHS = float(os.getenv("TAGLISH_MLM_EPOCHS", 2))
LEARNING_RATE = float(os.getenv("TAGLISH_MLM_LEARNING_RATE", 3e-5))
MLM_PROBABILITY = float(os.getenv("TAGLISH_MLM_PROBABILITY", 0.15))
SEED = int(os.getenv("TAGLISH_MLM_SEED", 42))
RESUME = os.getenv("TAGLISH_MLM_RESUME", "false").strip().lower() in {"1", "true", "yes"}


class TextDataset(Dataset):
    def __init__(self, texts, tokenizer):
        self.encodings = [
            tokenizer(text, truncation=True, max_length=MAX_LENGTH, return_special_tokens_mask=True)
            for text in texts
        ]

    def __len__(self):
        return len(self.encodings)

    def __getitem__(self, idx):
        return self.encodings[idx]


def load_texts() -> tuple[list[str], list[str]]:
    df = pd.read_csv(DATASET, usecols=["text", "split"])
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"] != ""].drop_duplicates(subset="text")
    train = df[df["split"] == "train"]["text"].tolist()
    test = df[df["split"] == "test"]["text"].tolist()
    return train, test


def build_mlm_model() -> BertForMaskedLM:
    # Encoder from the emotion checkpoint, MLM head from the base model it was
    # fine-tuned from. `bert.*` keys in the checkpoint load onto the encoder;
    # the classifier keys are ignored here and re-attached at save time.
    mlm = BertForMaskedLM.from_pretrained(MLM_HEAD_MODEL)
    classifier = AutoModelForSequenceClassification.from_pretrained(str(SOURCE_MODEL))
    missing, unexpected = mlm.bert.load_state_dict(classifier.bert.state_dict(), strict=False)
    # BertForMaskedLM's encoder has no pooler; that is the only expected mismatch.
    unexpected = [key for key in unexpected if not key.startswith("pooler.")]
    if missing or unexpected:
        raise RuntimeError(f"Encoder mismatch: missing={missing}, unexpected={unexpected}")
    mlm.tie_weights()
    return mlm


def evaluate_perplexity(trainer: Trainer) -> float:
    torch.manual_seed(SEED)  # same random masks for the before/after comparison
    loss = trainer.evaluate()["eval_loss"]
    return math.exp(loss)


def main() -> int:
    torch.manual_seed(SEED)
    print(f"Source encoder: {SOURCE_MODEL}")
    print(f"Dataset: {DATASET} (text column only; sentiment labels are not used)")

    tokenizer = AutoTokenizer.from_pretrained(str(SOURCE_MODEL))
    train_texts, test_texts = load_texts()
    print(f"FiReCS texts: train={len(train_texts)}, test={len(test_texts)}")

    train_dataset = TextDataset(train_texts, tokenizer)
    eval_dataset = TextDataset(test_texts, tokenizer)
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm_probability=MLM_PROBABILITY)

    model = build_mlm_model()
    args = TrainingArguments(
        output_dir=str(WORK_DIR),
        overwrite_output_dir=not RESUME,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE * 2,
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.06,
        weight_decay=0.01,
        group_by_length=True,
        # Step checkpoints, not epoch ones: an epoch here is ~an hour of CPU,
        # and earlier runs on this box lost whole epochs to a kill.
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        evaluation_strategy="no",
        # Only the loss is needed for perplexity. Without this, evaluate() keeps
        # every MLM logit (eval rows x 96 tokens x 30k vocab, ~36 GB) and the
        # run is OOM-killed on this 7 GB box.
        prediction_loss_only=True,
        logging_steps=25,
        report_to="none",
        seed=SEED,
        dataloader_pin_memory=False,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=collator,
    )

    resume_checkpoint = get_last_checkpoint(str(WORK_DIR)) if RESUME and WORK_DIR.is_dir() else None
    perplexity_before = None
    if resume_checkpoint:
        print(f"Resuming from {resume_checkpoint}")
        report_path = WORK_DIR / "perplexity_before.json"
        if report_path.is_file():
            perplexity_before = json.loads(report_path.read_text())["perplexity"]
    else:
        print("Measuring FiReCS test perplexity before adaptation...")
        perplexity_before = evaluate_perplexity(trainer)
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        (WORK_DIR / "perplexity_before.json").write_text(json.dumps({"perplexity": perplexity_before}))
    print(f"Perplexity before: {perplexity_before}")

    train_output = trainer.train(resume_from_checkpoint=resume_checkpoint)

    print("Measuring FiReCS test perplexity after adaptation...")
    perplexity_after = evaluate_perplexity(trainer)
    print(f"Perplexity after: {perplexity_after:.3f} (before: {perplexity_before})")

    # Put the adapted encoder back under the original classifier head.
    classifier = AutoModelForSequenceClassification.from_pretrained(str(SOURCE_MODEL))
    adapted_encoder = {k: v for k, v in trainer.model.bert.state_dict().items()}
    missing, unexpected = classifier.bert.load_state_dict(adapted_encoder, strict=False)
    missing = [key for key in missing if not key.startswith("pooler.")]
    if missing or unexpected:
        raise RuntimeError(f"Write-back mismatch: missing={missing}, unexpected={unexpected}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    classifier.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    report = {
        "source_model": str(SOURCE_MODEL.relative_to(REPO_ROOT)) if SOURCE_MODEL.is_relative_to(REPO_ROOT) else str(SOURCE_MODEL),
        "mlm_head_model": MLM_HEAD_MODEL,
        "dataset": str(DATASET.relative_to(REPO_ROOT)) if DATASET.is_relative_to(REPO_ROOT) else str(DATASET),
        "labels_used": False,
        "train_texts": len(train_texts),
        "eval_texts": len(test_texts),
        "epochs": EPOCHS,
        "learning_rate": LEARNING_RATE,
        "max_length": MAX_LENGTH,
        "mlm_probability": MLM_PROBABILITY,
        "eval_perplexity_before": perplexity_before,
        "eval_perplexity_after": perplexity_after,
        "train_metrics": train_output.metrics,
    }
    (OUTPUT_DIR / "taglish_adaptation.json").write_text(json.dumps(report, indent=2))
    print(f"Saved adapted classifier checkpoint to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
