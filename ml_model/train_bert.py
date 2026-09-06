#!/usr/bin/env python3
"""
EmoTune staged BERT fine-tuning pipeline.

Default sequence:
1. GoEmotions base fine-tune
2. Optional dair-ai/emotion adaptation
3. Text Emotion Classification 150k pre-training
4. EmoTune final fine-tune

Stages 1-3 are pre-training on outside corpora: they buy the model real-world
language, but none of them covers EmoTune's full 13-label schema. Stage 4 is
what makes every label reachable, which is why it always runs last.

The final evaluation is always reported on an EmoTune-only holdout split so the
metrics reflect the app's label schema and tone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_local_venv  # noqa: E402

ensure_local_venv('torch')

import numpy as np  # noqa: E402
import pandas as pd
import torch
from datasets import load_dataset
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)
from transformers.trainer_utils import get_last_checkpoint

from data_pipeline import DATASET_PATH, clean_dataset, load_custom_dataset, resolve_dataset_path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ml.emotion_labels import (  # noqa: E402
    GOEMOTIONS_LABEL_MAP,
    LABEL2ID,
    call_huggingface_loader as _call_huggingface_loader,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class TrainingConfig:
    """All environment-tunable training settings, resolved once at import time.

    Replaces what used to be ~15 separate `_env_*`-derived module globals. Every
    field is still re-exposed as a same-named module-level constant below (e.g.
    `SEED = CONFIG.seed`) so the rest of this script is unchanged and doesn't need
    to thread a config object through every function.
    """

    model_name: str
    output_dir: Path
    num_labels: int
    max_length: int
    batch_size: int
    gradient_accumulation_steps: int
    num_epochs: int
    learning_rate: float
    warmup_ratio: float
    seed: int
    max_samples_per_class: int
    custom_repeat_factor: int
    enable_goemotions: bool
    enable_dair_emotion: bool
    enable_text_emotion: bool
    enable_custom_final_stage: bool
    goemotions_stage_epochs: float
    dair_stage_epochs: float
    text_emotion_stage_epochs: float
    custom_stage_epochs: float
    resume: bool

    @classmethod
    def from_env(cls) -> "TrainingConfig":
        num_epochs = _env_int("EMOTUNE_NUM_EPOCHS", 5)
        return cls(
            model_name=os.getenv("EMOTUNE_MODEL_NAME", "bert-base-uncased"),
            output_dir=(
                Path(__file__).resolve().parent.parent
                / "backend"
                / "ml"
                / "models"
                / "bert_emotion_model"
            ),
            num_labels=13,
            max_length=_env_int("EMOTUNE_MAX_LENGTH", 128),
            batch_size=_env_int("EMOTUNE_BATCH_SIZE", 16),
            gradient_accumulation_steps=_env_int("EMOTUNE_GRADIENT_ACCUMULATION_STEPS", 1),
            num_epochs=num_epochs,
            learning_rate=_env_float("EMOTUNE_LEARNING_RATE", 2e-5),
            warmup_ratio=_env_float("EMOTUNE_WARMUP_RATIO", 0.1),
            seed=_env_int("EMOTUNE_SEED", 42),
            max_samples_per_class=_env_int("EMOTUNE_MAX_SAMPLES_PER_CLASS", 2000),
            custom_repeat_factor=_env_int("EMOTUNE_CUSTOM_REPEAT_FACTOR", 10),
            enable_goemotions=_env_bool("EMOTUNE_ENABLE_GOEMOTIONS", True),
            enable_dair_emotion=_env_bool("EMOTUNE_ENABLE_DAIR_EMOTION", False),
            enable_text_emotion=_env_bool("EMOTUNE_ENABLE_TEXT_EMOTION", True),
            enable_custom_final_stage=_env_bool("EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE", True),
            goemotions_stage_epochs=_env_float("EMOTUNE_GOEMOTIONS_EPOCHS", 1.0),
            dair_stage_epochs=_env_float("EMOTUNE_DAIR_EMOTION_EPOCHS", 1.0),
            text_emotion_stage_epochs=_env_float("EMOTUNE_TEXT_EMOTION_EPOCHS", 1.0),
            custom_stage_epochs=_env_float("EMOTUNE_FINAL_FINETUNE_EPOCHS", float(num_epochs)),
            resume=_env_bool("EMOTUNE_RESUME", False),
        )


CONFIG = TrainingConfig.from_env()

MODEL_NAME = CONFIG.model_name
OUTPUT_DIR = CONFIG.output_dir
NUM_LABELS = CONFIG.num_labels
MAX_LENGTH = CONFIG.max_length
BATCH_SIZE = CONFIG.batch_size
GRADIENT_ACCUMULATION_STEPS = CONFIG.gradient_accumulation_steps
NUM_EPOCHS = CONFIG.num_epochs
LEARNING_RATE = CONFIG.learning_rate
WARMUP_RATIO = CONFIG.warmup_ratio
SEED = CONFIG.seed
MAX_SAMPLES_PER_CLASS = CONFIG.max_samples_per_class
CUSTOM_REPEAT_FACTOR = CONFIG.custom_repeat_factor

ENABLE_GOEMOTIONS = CONFIG.enable_goemotions
ENABLE_DAIR_EMOTION = CONFIG.enable_dair_emotion
ENABLE_TEXT_EMOTION = CONFIG.enable_text_emotion
ENABLE_CUSTOM_FINAL_STAGE = CONFIG.enable_custom_final_stage

GOEMOTIONS_STAGE_EPOCHS = CONFIG.goemotions_stage_epochs
DAIR_STAGE_EPOCHS = CONFIG.dair_stage_epochs
TEXT_EMOTION_STAGE_EPOCHS = CONFIG.text_emotion_stage_epochs
CUSTOM_STAGE_EPOCHS = CONFIG.custom_stage_epochs

RESUME = CONFIG.resume

# Produced by ml_model/clean_text_emotion_dataset.py from the raw
# "Text Emotion Classification 150k" CSV. It is a pre-training stage, never the
# final one: it can only teach 7 of the 13 labels (it has no sad, stressed,
# lonely, depressing, nostalgic or mixed data at all), so the balanced EmoTune
# custom stage has to run after it to restore the full schema.
TEXT_EMOTION_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "dataset" / "text_emotion_classification.cleaned.csv"
)

# LABEL2ID and the GoEmotions mapping are the same schema the runtime classifier
# (backend/ml/emotion_classifier.py) uses at inference time, so both are imported
# from the shared backend/ml/emotion_labels.py module above rather than duplicated
# here. LABEL2ID's key order is baked into any already-saved model checkpoint's
# id2label config, so it must stay exactly as it was (verified identical).
ID2LABEL = {value: key for key, value in LABEL2ID.items()}

DAIR_EMOTION_MAP = {
    "anger": "angry",
    "fear": "fear",
    "joy": "happy",
    "love": "romantic",
    "sadness": "sad",
    "surprise": "surprising",
}

CUSTOM_DATASET = [
    ("I'm so happy today, everything is going great!", "happy"),
    ("Just got promoted at work! Best day ever!", "happy"),
    ("My team won the championship! I'm ecstatic!", "happy"),
    ("Got an A on my exam, feeling on top of the world!", "happy"),
    ("Birthday celebration with all my friends was amazing!", "happy"),
    ("My baby took their first steps today!", "happy"),
    ("Just finished my favorite book and the ending was perfect!", "happy"),
    ("I miss my grandmother so much. She passed away last year.", "sad"),
    ("My best friend is moving to another country. I feel lost.", "sad"),
    ("I cried watching that movie, it hit too close to home.", "sad"),
    ("Failed my exam after studying for weeks. So disappointed.", "sad"),
    ("Nobody remembered my birthday today.", "sad"),
    ("Looking at old photos makes me sad about how things changed.", "sad"),
    ("I can't believe they lied to me. I'm furious!", "angry"),
    ("This traffic is making me so mad. I'm going to be late again!", "angry"),
    ("My roommate keeps leaving dishes in the sink, I'm fed up!", "angry"),
    ("They canceled my favorite show. This is outrageous!", "angry"),
    ("Why do people keep interrupting me? I'm losing my patience.", "angry"),
    ("I'm going to crush this workout today! Nothing can stop me!", "motivational"),
    ("Every failure is just a stepping stone to success.", "motivational"),
    ("Starting my business today. Excited for this new chapter!", "motivational"),
    ("Going to study all night and ace this presentation!", "motivational"),
    ("I believe in myself. I can achieve anything I set my mind to!", "motivational"),
    ("Training for a marathon. No pain no gain!", "motivational"),
    ("I have my first job interview tomorrow. I'm terrified.", "fear"),
    ("There's a strange noise outside. I'm scared to check.", "fear"),
    ("I have anxiety about flying but I have a trip next week.", "fear"),
    ("Presenting in front of 500 people next week. Petrified.", "fear"),
    ("I'm worried something bad might happen to my family.", "fear"),
    ("I feel empty inside. Nothing brings me joy anymore.", "depressing"),
    ("What's the point of anything? I can't see the light.", "depressing"),
    ("I've been feeling numb for weeks. Everything feels grey.", "depressing"),
    ("I don't want to get out of bed. Life feels meaningless.", "depressing"),
    ("I feel like I'm just going through the motions every day.", "depressing"),
    ("The darkness inside me won't go away no matter what I do.", "depressing"),
    ("I just found out I'm pregnant! Complete shock!", "surprising"),
    ("My long lost sibling just called me out of nowhere!", "surprising"),
    ("Won the lottery today. I still can't believe it!", "surprising"),
    ("My boss just gave me an unexpected bonus. What a surprise!", "surprising"),
    ("Ran into my childhood friend at the airport in another country!", "surprising"),
    ("I have three deadlines tomorrow and I haven't started any of them.", "stressed"),
    ("My boss wants the report in an hour. I'm overwhelmed.", "stressed"),
    ("Balancing work, school, and family is burning me out.", "stressed"),
    ("I can't sleep because I'm thinking about everything I need to do.", "stressed"),
    ("Finals week is here and I feel like I'm drowning.", "stressed"),
    ("Too many responsibilities, not enough time. Completely overwhelmed.", "stressed"),
    ("Just finished meditating. Feeling so peaceful and centered.", "calm"),
    ("Sitting by the ocean and watching the sunset. Pure bliss.", "calm"),
    ("Everything is in order and I feel at peace with the world.", "calm"),
    ("Reading a good book with a cup of tea. Perfectly content.", "calm"),
    ("A quiet Sunday morning with no plans. This is what I needed.", "calm"),
    ("I have 500 friends on social media but I feel completely alone.", "lonely"),
    ("Moved to a new city and don't know anyone here.", "lonely"),
    ("Everyone seems to have their own lives. Nobody checks on me.", "lonely"),
    ("Sitting at home alone on a Friday night. Missing connection.", "lonely"),
    ("Even in a crowd I feel isolated and invisible.", "lonely"),
    ("I'm so in love. Every moment with them feels magical.", "romantic"),
    ("Got flowers from my partner unexpectedly. My heart is full.", "romantic"),
    ("Planning a surprise date for my anniversary. Love is beautiful.", "romantic"),
    ("The way they look at me makes me feel like the only person in the world.", "romantic"),
    ("First date tonight! I have butterflies!", "romantic"),
    ("Heard that song from 2008 and suddenly I'm 16 again.", "nostalgic"),
    ("Found my old diary. Remembering who I used to be.", "nostalgic"),
    ("Drove past my childhood home today. So many memories.", "nostalgic"),
    ("Rewatching old cartoons from my childhood. Simpler times.", "nostalgic"),
    ("Old photos with friends I've lost touch with. Miss those days.", "nostalgic"),
    ("I got the job offer but it means leaving my family behind.", "mixed"),
    ("Happy it's my birthday but also reflecting on time passing.", "mixed"),
    ("Graduated today! Proud but nervous about what comes next.", "mixed"),
    ("My relationship ended. Sad but also relieved somehow.", "mixed"),
    ("Moving to my dream city but terrified of starting over.", "mixed"),
]


@dataclass
class PreparedStage:
    name: str
    description: str
    num_epochs: float
    train_texts: list[str]
    train_labels: list[int]
    eval_texts: list[str]
    eval_labels: list[int]
    metadata: dict = field(default_factory=dict)


class EmotionDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length: int = MAX_LENGTH):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {key: value[idx] for key, value in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


class WeightedTrainer(Trainer):
    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get("logits")
        loss_fct = torch.nn.CrossEntropyLoss(
            weight=self.class_weights.to(logits.device)
            if self.class_weights is not None
            else None
        )
        loss = loss_fct(logits.view(-1, model.config.num_labels), labels.view(-1))
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    accuracy = accuracy_score(labels, predictions)
    precision = precision_score(labels, predictions, average="weighted", zero_division=0)
    recall = recall_score(labels, predictions, average="weighted", zero_division=0)
    f1 = f1_score(labels, predictions, average="weighted", zero_division=0)
    macro_f1 = f1_score(labels, predictions, average="macro", zero_division=0)
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "macro_f1": macro_f1,
    }


def _label_distribution(label_ids: list[int]) -> dict:
    series = pd.Series(label_ids, dtype="int64")
    return {
        ID2LABEL[label_id]: int(count)
        for label_id, count in series.value_counts().sort_index().items()
    }


def _normalize_metrics(metrics: dict) -> dict:
    normalized = {}
    for key, value in metrics.items():
        if isinstance(value, (np.floating, float)):
            normalized[key] = float(value)
        elif isinstance(value, (np.integer, int)):
            normalized[key] = int(value)
        else:
            normalized[key] = value
    return normalized


def _to_label_ids(label_names: list[str]) -> list[int]:
    return [LABEL2ID[label_name] for label_name in label_names]


def _stratified_split_with_fallback(
    df: pd.DataFrame, *, test_size: float, random_state: int, stratify_column: str = "emotion"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified split, falling back to a plain split when a class is too small.

    The EmoTune custom dataset has few unique rows per emotion after
    deduplication, so a second stratified split on an already-small holdout
    can leave a class with only 1 member -- which sklearn rejects outright.
    Preserving class balance on that tiny holdout isn't worth crashing the
    whole training run over, so fall back to an unstratified split instead.

    `stratify_column` exists because the pre-training stages carry integer
    `label` ids rather than the custom stage's `emotion` names.
    """
    try:
        return train_test_split(
            df,
            test_size=test_size,
            random_state=random_state,
            stratify=df[stratify_column],
        )
    except ValueError:
        return train_test_split(df, test_size=test_size, random_state=random_state)


def _build_text_label_df(texts: list[str], label_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"text": texts, "label": label_ids})


class StageDataPreparer:
    """Builds the per-source PreparedStage objects consumed by BertEmotionTrainer."""

    def __init__(self, config: TrainingConfig = CONFIG):
        self.config = config

    def build_stage_sequence(self) -> tuple[list[PreparedStage], pd.DataFrame | None]:
        stages: list[PreparedStage] = []
        custom_test_df: pd.DataFrame | None = None

        if self.config.enable_goemotions:
            go_stage = self.prepare_goemotions_stage()
            if go_stage is not None:
                stages.append(go_stage)

        if self.config.enable_dair_emotion:
            dair_stage = self.prepare_dair_stage()
            if dair_stage is not None:
                stages.append(dair_stage)

        if self.config.enable_text_emotion:
            text_emotion_stage = self.prepare_text_emotion_stage()
            if text_emotion_stage is not None:
                stages.append(text_emotion_stage)

        if self.config.enable_custom_final_stage:
            custom_stage, custom_test_df = self.prepare_custom_stage()
            if custom_stage is not None:
                stages.append(custom_stage)

        return stages, custom_test_df

    def prepare_goemotions_stage(self) -> PreparedStage | None:
        print("Loading GoEmotions dataset...")
        try:
            dataset = load_dataset("go_emotions", "simplified")
        except Exception as error:
            print(f"Could not load GoEmotions: {error}")
            return None

        label_names = dataset["train"].features["labels"].feature.names
        train_texts, train_labels = self._split_goemotions_split(dataset["train"], label_names)
        eval_texts, eval_labels = self._split_goemotions_split(dataset["validation"], label_names)

        train_df = self._cap_per_class(_build_text_label_df(train_texts, train_labels), self.config.max_samples_per_class)
        eval_df = self._cap_per_class(_build_text_label_df(eval_texts, eval_labels), self.config.max_samples_per_class)

        print(f"Loaded {len(train_df)} GoEmotions training samples after mapping/capping")
        print(f"Loaded {len(eval_df)} GoEmotions validation samples after mapping/capping")

        return PreparedStage(
            name="goemotions",
            description="GoEmotions base fine-tune",
            num_epochs=self.config.goemotions_stage_epochs,
            train_texts=train_df["text"].tolist(),
            train_labels=train_df["label"].astype(int).tolist(),
            eval_texts=eval_df["text"].tolist(),
            eval_labels=eval_df["label"].astype(int).tolist(),
            metadata={
                "source_dataset": "go_emotions/simplified",
                "train_label_distribution": _label_distribution(train_df["label"].astype(int).tolist()),
                "eval_label_distribution": _label_distribution(eval_df["label"].astype(int).tolist()),
            },
        )

    @staticmethod
    def _split_goemotions_split(split, label_names: list[str]) -> tuple[list[str], list[int]]:
        texts: list[str] = []
        labels: list[int] = []

        for item in split:
            mapped_label = None
            for label_id in item["labels"]:
                candidate = GOEMOTIONS_LABEL_MAP.get(label_names[label_id])
                if candidate:
                    mapped_label = candidate
                    break

            if not mapped_label:
                continue

            texts.append(item["text"])
            labels.append(LABEL2ID[mapped_label])

        return texts, labels

    def prepare_dair_stage(self) -> PreparedStage | None:
        print("Loading dair-ai/emotion dataset...")
        try:
            dataset = load_dataset("dair-ai/emotion")
        except Exception as error:
            print(f"Could not load dair-ai/emotion: {error}")
            return None

        label_names = dataset["train"].features["label"].names
        train_texts, train_labels = self._split_dair_split(dataset["train"], label_names)
        eval_texts, eval_labels = self._split_dair_split(dataset["validation"], label_names)

        train_df = self._cap_per_class(_build_text_label_df(train_texts, train_labels), self.config.max_samples_per_class)
        eval_df = self._cap_per_class(_build_text_label_df(eval_texts, eval_labels), self.config.max_samples_per_class)

        print(f"Loaded {len(train_df)} dair-ai/emotion training samples after mapping/capping")
        print(f"Loaded {len(eval_df)} dair-ai/emotion validation samples after mapping/capping")

        return PreparedStage(
            name="dair_emotion",
            description="dair-ai/emotion adaptation",
            num_epochs=self.config.dair_stage_epochs,
            train_texts=train_df["text"].tolist(),
            train_labels=train_df["label"].astype(int).tolist(),
            eval_texts=eval_df["text"].tolist(),
            eval_labels=eval_df["label"].astype(int).tolist(),
            metadata={
                "source_dataset": "dair-ai/emotion",
                "train_label_distribution": _label_distribution(train_df["label"].astype(int).tolist()),
                "eval_label_distribution": _label_distribution(eval_df["label"].astype(int).tolist()),
            },
        )

    @staticmethod
    def _split_dair_split(split, label_names: list[str]) -> tuple[list[str], list[int]]:
        texts: list[str] = []
        labels: list[int] = []

        for item in split:
            mapped = DAIR_EMOTION_MAP.get(label_names[item["label"]])
            if not mapped:
                continue
            texts.append(item["text"])
            labels.append(LABEL2ID[mapped])

        return texts, labels

    def prepare_text_emotion_stage(self) -> PreparedStage | None:
        """Pre-train on the cleaned Text Emotion Classification 150k corpus.

        The cleaner leaves ~92.5k rows but they are wildly unbalanced (43.9k
        happy against 66 surprising), so `_cap_per_class` does real work here --
        without it the stage would simply teach the model to answer "happy".
        Capping at the default 2,000 turns it into a roughly even 7-label
        pre-training set of real human sentences, which is exactly what the
        current undertrained model is short of.
        """
        dataset_path = TEXT_EMOTION_DATASET_PATH
        if not dataset_path.exists():
            print(
                f"Cleaned text-emotion dataset not found at {dataset_path}. "
                "Run ml_model/clean_text_emotion_dataset.py first. Skipping stage."
            )
            return None

        print(f"Loading cleaned text-emotion dataset from {dataset_path.name}...")
        try:
            raw_df = pd.read_csv(dataset_path)
        except Exception as error:
            print(f"Could not read {dataset_path.name}: {error}")
            return None

        if "text" not in raw_df.columns or "emotion" not in raw_df.columns:
            print(f"{dataset_path.name} must have 'text' and 'emotion' columns. Skipping stage.")
            return None

        raw_df = raw_df.dropna(subset=["text", "emotion"])
        raw_df = raw_df[raw_df["emotion"].isin(LABEL2ID)]
        if raw_df.empty:
            print("Cleaned text-emotion dataset has no usable rows. Skipping stage.")
            return None

        frame = _build_text_label_df(
            raw_df["text"].astype(str).tolist(),
            _to_label_ids(raw_df["emotion"].astype(str).tolist()),
        )
        train_df, eval_df = _stratified_split_with_fallback(
            frame, test_size=0.1, random_state=self.config.seed, stratify_column="label"
        )
        train_df = self._cap_per_class(train_df, self.config.max_samples_per_class)
        eval_df = self._cap_per_class(eval_df, max(self.config.max_samples_per_class // 10, 1))

        print(f"Loaded {len(train_df)} text-emotion training samples after capping")
        print(f"Loaded {len(eval_df)} text-emotion validation samples after capping")

        return PreparedStage(
            name="text_emotion_150k",
            description="Text Emotion Classification 150k pre-training",
            num_epochs=self.config.text_emotion_stage_epochs,
            train_texts=train_df["text"].tolist(),
            train_labels=train_df["label"].astype(int).tolist(),
            eval_texts=eval_df["text"].tolist(),
            eval_labels=eval_df["label"].astype(int).tolist(),
            metadata={
                "source_dataset": dataset_path.name,
                "rows_before_capping": int(len(frame)),
                "max_samples_per_class": self.config.max_samples_per_class,
                "train_label_distribution": _label_distribution(train_df["label"].astype(int).tolist()),
                "eval_label_distribution": _label_distribution(eval_df["label"].astype(int).tolist()),
            },
        )

    def prepare_custom_stage(self) -> tuple[PreparedStage | None, pd.DataFrame | None]:
        custom_df, data_report = self._load_clean_custom_dataframe()
        if custom_df.empty:
            print("Custom EmoTune dataset is empty. Skipping final fine-tune stage.")
            return None, None

        train_df, temp_df = _stratified_split_with_fallback(
            custom_df, test_size=0.15, random_state=self.config.seed
        )
        eval_df, test_df = _stratified_split_with_fallback(
            temp_df, test_size=0.5, random_state=self.config.seed
        )

        if self.config.custom_repeat_factor > 1:
            train_df = pd.concat([train_df] * self.config.custom_repeat_factor, ignore_index=True)

        train_label_ids = _to_label_ids(train_df["emotion"].tolist())
        eval_label_ids = _to_label_ids(eval_df["emotion"].tolist())
        test_df = test_df.reset_index(drop=True)

        print(
            "Prepared EmoTune custom split: "
            f"train={len(train_df)}, validation={len(eval_df)}, test={len(test_df)}"
        )

        stage = PreparedStage(
            name="emotune_custom",
            description="EmoTune final fine-tune",
            num_epochs=self.config.custom_stage_epochs,
            train_texts=train_df["text"].tolist(),
            train_labels=train_label_ids,
            eval_texts=eval_df["text"].tolist(),
            eval_labels=eval_label_ids,
            metadata={
                "source_dataset": str(resolve_dataset_path(DATASET_PATH).name),
                "custom_repeat_factor": self.config.custom_repeat_factor,
                "train_label_distribution": _label_distribution(train_label_ids),
                "eval_label_distribution": _label_distribution(eval_label_ids),
                "data_report": data_report,
            },
        )
        return stage, test_df

    def _load_clean_custom_dataframe(self) -> tuple[pd.DataFrame, dict]:
        dataset_path = resolve_dataset_path(DATASET_PATH)
        try:
            custom_df = load_custom_dataset(dataset_path)
            cleaned_df, data_report = clean_dataset(custom_df)
            print(f"Loaded {len(cleaned_df)} cleaned custom samples from {dataset_path}")
            print(f"Removed {data_report['rows_removed']} invalid/duplicate custom rows during cleaning")
            data_report['dataset_path'] = str(dataset_path)
            return cleaned_df[["text", "emotion"]].copy(), data_report
        except Exception as error:
            print(f"Could not load custom dataset CSV: {error}. Falling back to in-script samples.")
            fallback_df = pd.DataFrame(CUSTOM_DATASET, columns=["text", "emotion"])
            return fallback_df, {
                "source_dataset": "in_script_fallback",
                "rows_after_cleaning": int(len(fallback_df)),
                "rows_removed": 0,
            }

    def _cap_per_class(self, df: pd.DataFrame, max_samples_per_class: int) -> pd.DataFrame:
        if df.empty or max_samples_per_class <= 0:
            return df.reset_index(drop=True)

        capped = []
        for label_id in sorted(df["label"].unique()):
            class_df = df[df["label"] == label_id]
            if len(class_df) > max_samples_per_class:
                class_df = class_df.sample(max_samples_per_class, random_state=self.config.seed)
            capped.append(class_df)

        if not capped:
            return df.iloc[0:0].copy()

        return pd.concat(capped).sample(frac=1, random_state=self.config.seed).reset_index(drop=True)


class BertEmotionTrainer:
    """Orchestrates the staged fine-tuning run: load base model, train each stage, evaluate, save."""

    def __init__(self, config: TrainingConfig = CONFIG, data_preparer: "StageDataPreparer | None" = None):
        self.config = config
        self.data_preparer = data_preparer or StageDataPreparer(config)

    def run(self):
        print("=" * 60)
        print("EmoTune Staged BERT Fine-Tuning")
        print("=" * 60)
        print(
            f"Config: model={self.config.model_name}, batch_size={self.config.batch_size}, "
            f"max_length={self.config.max_length}, learning_rate={self.config.learning_rate}, "
            f"max_per_class={self.config.max_samples_per_class}"
        )
        print(
            "Stage toggles: "
            f"goemotions={self.config.enable_goemotions}, "
            f"dair_ai_emotion={self.config.enable_dair_emotion}, "
            f"text_emotion_150k={self.config.enable_text_emotion}, "
            f"emotune_final={self.config.enable_custom_final_stage}"
        )

        np.random.seed(self.config.seed)
        torch.manual_seed(self.config.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.config.seed)

        stages, custom_test_df = self.data_preparer.build_stage_sequence()
        if not stages:
            raise RuntimeError("No training stages were prepared. Check dataset availability and stage toggles.")

        print("\nStage order:")
        for index, stage in enumerate(stages, start=1):
            print(f"  {index}. {stage.description} ({stage.num_epochs} epochs)")

        print(f"\nLoading base model: {self.config.model_name}")
        tokenizer = _call_huggingface_loader(AutoTokenizer.from_pretrained, self.config.model_name)
        model = _call_huggingface_loader(
            AutoModelForSequenceClassification.from_pretrained,
            self.config.model_name,
            num_labels=self.config.num_labels,
            id2label=ID2LABEL,
            label2id=LABEL2ID,
        )

        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        stage_summaries = []
        for index, stage in enumerate(stages):
            model, stage_summary = self._train_stage(model, tokenizer, stage, index)
            stage_summaries.append(stage_summary)

        print("\nSaving final model...")
        model.save_pretrained(str(self.config.output_dir))
        tokenizer.save_pretrained(str(self.config.output_dir))

        final_results = {}
        prediction_dump = {}
        if custom_test_df is not None and not custom_test_df.empty:
            final_results, prediction_dump = self._evaluate_final_model(model, tokenizer, custom_test_df)
        else:
            print("\nSkipping final EmoTune evaluation because no custom test split was available.")

        results_payload = {
            "seed": self.config.seed,
            "model_name": self.config.model_name,
            "stage_sequence": [summary["stage"] for summary in stage_summaries],
            "stage_summaries": stage_summaries,
            "final_results": final_results,
            "config": {
                "batch_size": self.config.batch_size,
                "max_length": self.config.max_length,
                "learning_rate": self.config.learning_rate,
                "warmup_ratio": self.config.warmup_ratio,
                "max_samples_per_class": self.config.max_samples_per_class,
                "custom_repeat_factor": self.config.custom_repeat_factor,
                "enable_goemotions": self.config.enable_goemotions,
                "enable_dair_emotion": self.config.enable_dair_emotion,
                "enable_text_emotion": self.config.enable_text_emotion,
                "enable_custom_final_stage": self.config.enable_custom_final_stage,
                "goemotions_stage_epochs": self.config.goemotions_stage_epochs,
                "dair_stage_epochs": self.config.dair_stage_epochs,
                "text_emotion_stage_epochs": self.config.text_emotion_stage_epochs,
                "custom_stage_epochs": self.config.custom_stage_epochs,
            },
        }

        with open(self.config.output_dir / "training_results.json", "w", encoding="utf-8") as handle:
            json.dump(results_payload, handle, indent=2)

        if prediction_dump:
            with open(self.config.output_dir / "test_predictions.json", "w", encoding="utf-8") as handle:
                json.dump(prediction_dump, handle, indent=2)

        print(f"\nFinal model saved to: {self.config.output_dir}")
        if final_results:
            print(f"EmoTune Test Accuracy: {final_results['test_accuracy']:.4f}")
            print(f"EmoTune Weighted F1: {final_results['weighted_f1']:.4f}")
        print("\nTraining complete!")

    def _build_class_weights(self, label_ids: list[int]) -> torch.Tensor:
        weights = np.ones(self.config.num_labels, dtype=np.float32)
        if not label_ids:
            return torch.tensor(weights, dtype=torch.float)

        unique_labels = np.array(sorted(set(label_ids)))
        computed = compute_class_weight(
            class_weight="balanced",
            classes=unique_labels,
            y=np.array(label_ids),
        )
        for label_id, weight in zip(unique_labels, computed):
            weights[int(label_id)] = float(weight)
        return torch.tensor(weights, dtype=torch.float)

    def _stage_output_dir(self, stage: PreparedStage, stage_index: int) -> Path:
        return self.config.output_dir / f"stage_{stage_index + 1}_{stage.name}"

    def _build_training_args(self, stage: PreparedStage, stage_index: int) -> TrainingArguments:
        stage_output_dir = self._stage_output_dir(stage, stage_index)
        return TrainingArguments(
            output_dir=str(stage_output_dir),
            # Wiping the stage directory is the right default, but it would also
            # delete the checkpoint an EMOTUNE_RESUME run is about to pick up.
            overwrite_output_dir=not self.config.resume,
            num_train_epochs=stage.num_epochs,
            per_device_train_batch_size=self.config.batch_size,
            per_device_eval_batch_size=self.config.batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            warmup_ratio=self.config.warmup_ratio,
            weight_decay=0.01,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            load_best_model_at_end=True,
            metric_for_best_model="f1",
            logging_dir=str(stage_output_dir / "logs"),
            logging_steps=50,
            report_to="none",
            fp16=torch.cuda.is_available(),
            seed=self.config.seed,
        )

    def _train_stage(self, model, tokenizer, stage: PreparedStage, stage_index: int) -> tuple[object, dict]:
        print("\n" + "=" * 60)
        print(f"Stage {stage_index + 1}: {stage.description}")
        print("=" * 60)
        print(
            f"Examples: train={len(stage.train_texts)}, "
            f"validation={len(stage.eval_texts)}, epochs={stage.num_epochs}"
        )
        print(f"Train label distribution: {stage.metadata.get('train_label_distribution', {})}")
        print(f"Validation label distribution: {stage.metadata.get('eval_label_distribution', {})}")

        train_dataset = EmotionDataset(stage.train_texts, stage.train_labels, tokenizer)
        eval_dataset = EmotionDataset(stage.eval_texts, stage.eval_labels, tokenizer)
        class_weights = self._build_class_weights(stage.train_labels)

        trainer = WeightedTrainer(
            model=model,
            args=self._build_training_args(stage, stage_index),
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            compute_metrics=compute_metrics,
            class_weights=class_weights,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
        )

        # Checkpoints land once per epoch (save_strategy="epoch"), so a run
        # killed mid-stage restarts from the last completed epoch rather than
        # from the base model -- hours of CPU training, on this project.
        resume_checkpoint = self._find_resume_checkpoint(stage, stage_index)
        if resume_checkpoint:
            print(f"Resuming from checkpoint: {resume_checkpoint}")

        train_output = trainer.train(resume_from_checkpoint=resume_checkpoint)
        eval_metrics = trainer.evaluate()
        stage_summary = {
            "stage": stage.name,
            "description": stage.description,
            "num_epochs": float(stage.num_epochs),
            "train_examples": len(stage.train_texts),
            "validation_examples": len(stage.eval_texts),
            "train_metrics": _normalize_metrics(train_output.metrics),
            "validation_metrics": _normalize_metrics(eval_metrics),
            "class_weights": {
                ID2LABEL[index]: round(float(weight), 6)
                for index, weight in enumerate(class_weights.tolist())
            },
            "metadata": stage.metadata,
        }
        return trainer.model, stage_summary

    def _find_resume_checkpoint(self, stage: PreparedStage, stage_index: int) -> str | None:
        """Latest checkpoint for this stage, when EMOTUNE_RESUME asks for one.

        Opt-in rather than automatic: a stale directory from an earlier run with
        different data or hyper-parameters would otherwise be resumed silently,
        and the resulting model would not match the config it reports.
        """
        if not self.config.resume:
            return None

        stage_output_dir = self._stage_output_dir(stage, stage_index)
        if not stage_output_dir.is_dir():
            return None
        return get_last_checkpoint(str(stage_output_dir))

    def _evaluate_final_model(self, model, tokenizer, test_df: pd.DataFrame) -> tuple[dict, dict]:
        test_label_ids = _to_label_ids(test_df["emotion"].tolist())
        test_dataset = EmotionDataset(test_df["text"].tolist(), test_label_ids, tokenizer)

        trainer = Trainer(model=model)
        predictions = trainer.predict(test_dataset)
        predicted_ids = np.argmax(predictions.predictions, axis=-1)
        label_order = list(range(self.config.num_labels))

        report_text = classification_report(
            test_label_ids,
            predicted_ids,
            labels=label_order,
            target_names=[ID2LABEL[index] for index in label_order],
            zero_division=0,
        )
        print("\n" + "=" * 40)
        print("EMOTUNE TEST SET EVALUATION")
        print("=" * 40)
        print(report_text)

        results = {
            "test_accuracy": float(np.mean(predicted_ids == test_label_ids)),
            "weighted_f1": float(
                f1_score(test_label_ids, predicted_ids, average="weighted", zero_division=0)
            ),
            "macro_f1": float(
                f1_score(test_label_ids, predicted_ids, average="macro", zero_division=0)
            ),
            "test_label_distribution": _label_distribution(test_label_ids),
            "confusion_matrix": confusion_matrix(
                test_label_ids,
                predicted_ids,
                labels=label_order,
            ).tolist(),
            "confusion_matrix_labels": [ID2LABEL[index] for index in label_order],
            "classification_report": classification_report(
                test_label_ids,
                predicted_ids,
                labels=label_order,
                target_names=[ID2LABEL[index] for index in label_order],
                output_dict=True,
                zero_division=0,
            ),
        }
        return results, {
            "predicted_ids": predicted_ids.tolist(),
            "target_ids": list(test_label_ids),
        }


def train():
    BertEmotionTrainer().run()


def _parse_args(argv=None):
    """Accept --help without training.

    Every knob here is an environment variable, so this parser takes no
    options -- but it still has to exist. Without it an unrecognised argument
    was silently ignored and the script fell straight through to a multi-hour
    training run, so `train_bert.py --help` started training instead of
    printing help. Anything that probes scripts for a usage string (a smoke
    check, a person guessing) would set a full run going by accident.
    """
    parser = argparse.ArgumentParser(
        prog="train_bert.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Configuration is by environment variable, not flags:\n"
            "  EMOTUNE_DATASET_PATH             final-stage CSV "
            "(default dataset/emotune_custom_dataset.csv)\n"
            "  EMOTUNE_MODEL_NAME               base checkpoint "
            "(default bert-base-uncased)\n"
            "  EMOTUNE_NUM_EPOCHS               final-stage epochs (default 5)\n"
            "  EMOTUNE_BATCH_SIZE               default 16\n"
            "  EMOTUNE_MAX_LENGTH               default 128\n"
            "  EMOTUNE_LEARNING_RATE            default 2e-5\n"
            "  EMOTUNE_MAX_SAMPLES_PER_CLASS    per-class cap on pre-training "
            "stages (default 2000)\n"
            "  EMOTUNE_CUSTOM_REPEAT_FACTOR     repeats the final train split "
            "(default 10)\n"
            "  EMOTUNE_ENABLE_GOEMOTIONS        default true\n"
            "  EMOTUNE_ENABLE_DAIR_EMOTION      default false\n"
            "  EMOTUNE_ENABLE_TEXT_EMOTION      default true\n"
            "  EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE  default true\n"
            "  EMOTUNE_RESUME                   restart each stage from its "
            "last epoch checkpoint (default false)\n"
            "\nRunning it trains: on CPU that is hours, not seconds."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    _parse_args()
    train()
