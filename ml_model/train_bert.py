"""
EmoTune staged BERT fine-tuning pipeline.

Default sequence:
1. GoEmotions base fine-tune
2. Optional dair-ai/emotion adaptation
3. EmoTune final fine-tune

The final evaluation is always reported on an EmoTune-only holdout split so the
metrics reflect the app's label schema and tone.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
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

from data_pipeline import DATASET_PATH, clean_dataset, load_custom_dataset, resolve_dataset_path

warnings.filterwarnings("ignore")


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


MODEL_NAME = os.getenv("EMOTUNE_MODEL_NAME", "bert-base-uncased")
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "ml"
    / "models"
    / "bert_emotion_model"
)
NUM_LABELS = 13
MAX_LENGTH = _env_int("EMOTUNE_MAX_LENGTH", 128)
BATCH_SIZE = _env_int("EMOTUNE_BATCH_SIZE", 16)
NUM_EPOCHS = _env_int("EMOTUNE_NUM_EPOCHS", 5)
LEARNING_RATE = _env_float("EMOTUNE_LEARNING_RATE", 2e-5)
WARMUP_RATIO = _env_float("EMOTUNE_WARMUP_RATIO", 0.1)
SEED = _env_int("EMOTUNE_SEED", 42)
MAX_SAMPLES_PER_CLASS = _env_int("EMOTUNE_MAX_SAMPLES_PER_CLASS", 2000)
CUSTOM_REPEAT_FACTOR = _env_int("EMOTUNE_CUSTOM_REPEAT_FACTOR", 10)

ENABLE_GOEMOTIONS = _env_bool("EMOTUNE_ENABLE_GOEMOTIONS", True)
ENABLE_DAIR_EMOTION = _env_bool("EMOTUNE_ENABLE_DAIR_EMOTION", False)
ENABLE_CUSTOM_FINAL_STAGE = _env_bool("EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE", True)

GOEMOTIONS_STAGE_EPOCHS = _env_float("EMOTUNE_GOEMOTIONS_EPOCHS", 1.0)
DAIR_STAGE_EPOCHS = _env_float("EMOTUNE_DAIR_EMOTION_EPOCHS", 1.0)
CUSTOM_STAGE_EPOCHS = _env_float("EMOTUNE_FINAL_FINETUNE_EPOCHS", float(NUM_EPOCHS))

LABEL2ID = {
    "happy": 0,
    "sad": 1,
    "angry": 2,
    "motivational": 3,
    "fear": 4,
    "depressing": 5,
    "surprising": 6,
    "stressed": 7,
    "calm": 8,
    "lonely": 9,
    "romantic": 10,
    "nostalgic": 11,
    "mixed": 12,
}
ID2LABEL = {value: key for key, value in LABEL2ID.items()}

GOEMOTIONS_MAP = {
    "admiration": "happy",
    "amusement": "happy",
    "approval": "happy",
    "caring": "romantic",
    "confusion": "mixed",
    "curiosity": "surprising",
    "desire": "romantic",
    "disappointment": "sad",
    "disapproval": "angry",
    "disgust": "angry",
    "embarrassment": "sad",
    "excitement": "happy",
    "fear": "fear",
    "gratitude": "happy",
    "grief": "sad",
    "joy": "happy",
    "love": "romantic",
    "neutral": "calm",
    "nervousness": "fear",
    "optimism": "motivational",
    "pride": "motivational",
    "realization": "surprising",
    "relief": "calm",
    "remorse": "sad",
    "sadness": "sad",
    "surprise": "surprising",
    "anger": "angry",
    "annoyance": "angry",
    "boredom": "mixed",
}

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


def _cap_per_class(df: pd.DataFrame, max_samples_per_class: int) -> pd.DataFrame:
    if df.empty or max_samples_per_class <= 0:
        return df.reset_index(drop=True)

    capped = []
    for label_id in sorted(df["label"].unique()):
        class_df = df[df["label"] == label_id]
        if len(class_df) > max_samples_per_class:
            class_df = class_df.sample(max_samples_per_class, random_state=SEED)
        capped.append(class_df)

    if not capped:
        return df.iloc[0:0].copy()

    return pd.concat(capped).sample(frac=1, random_state=SEED).reset_index(drop=True)


def _build_text_label_df(texts: list[str], label_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"text": texts, "label": label_ids})


def _split_goemotions_split(split, label_names: list[str]) -> tuple[list[str], list[int]]:
    texts: list[str] = []
    labels: list[int] = []

    for item in split:
        mapped_label = None
        for label_id in item["labels"]:
            candidate = GOEMOTIONS_MAP.get(label_names[label_id])
            if candidate:
                mapped_label = candidate
                break

        if not mapped_label:
            continue

        texts.append(item["text"])
        labels.append(LABEL2ID[mapped_label])

    return texts, labels


def prepare_goemotions_stage() -> PreparedStage | None:
    print("Loading GoEmotions dataset...")
    try:
        dataset = load_dataset("go_emotions", "simplified")
    except Exception as error:
        print(f"Could not load GoEmotions: {error}")
        return None

    label_names = dataset["train"].features["labels"].feature.names
    train_texts, train_labels = _split_goemotions_split(dataset["train"], label_names)
    eval_texts, eval_labels = _split_goemotions_split(dataset["validation"], label_names)

    train_df = _cap_per_class(_build_text_label_df(train_texts, train_labels), MAX_SAMPLES_PER_CLASS)
    eval_df = _cap_per_class(_build_text_label_df(eval_texts, eval_labels), MAX_SAMPLES_PER_CLASS)

    print(f"Loaded {len(train_df)} GoEmotions training samples after mapping/capping")
    print(f"Loaded {len(eval_df)} GoEmotions validation samples after mapping/capping")

    return PreparedStage(
        name="goemotions",
        description="GoEmotions base fine-tune",
        num_epochs=GOEMOTIONS_STAGE_EPOCHS,
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


def prepare_dair_stage() -> PreparedStage | None:
    print("Loading dair-ai/emotion dataset...")
    try:
        dataset = load_dataset("dair-ai/emotion")
    except Exception as error:
        print(f"Could not load dair-ai/emotion: {error}")
        return None

    label_names = dataset["train"].features["label"].names
    train_texts, train_labels = _split_dair_split(dataset["train"], label_names)
    eval_texts, eval_labels = _split_dair_split(dataset["validation"], label_names)

    train_df = _cap_per_class(_build_text_label_df(train_texts, train_labels), MAX_SAMPLES_PER_CLASS)
    eval_df = _cap_per_class(_build_text_label_df(eval_texts, eval_labels), MAX_SAMPLES_PER_CLASS)

    print(f"Loaded {len(train_df)} dair-ai/emotion training samples after mapping/capping")
    print(f"Loaded {len(eval_df)} dair-ai/emotion validation samples after mapping/capping")

    return PreparedStage(
        name="dair_emotion",
        description="dair-ai/emotion adaptation",
        num_epochs=DAIR_STAGE_EPOCHS,
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


def _load_clean_custom_dataframe() -> tuple[pd.DataFrame, dict]:
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


def prepare_custom_stage() -> tuple[PreparedStage | None, pd.DataFrame | None]:
    custom_df, data_report = _load_clean_custom_dataframe()
    if custom_df.empty:
        print("Custom EmoTune dataset is empty. Skipping final fine-tune stage.")
        return None, None

    train_df, temp_df = train_test_split(
        custom_df,
        test_size=0.15,
        random_state=SEED,
        stratify=custom_df["emotion"],
    )
    eval_df, test_df = train_test_split(
        temp_df,
        test_size=0.5,
        random_state=SEED,
        stratify=temp_df["emotion"],
    )

    if CUSTOM_REPEAT_FACTOR > 1:
        train_df = pd.concat([train_df] * CUSTOM_REPEAT_FACTOR, ignore_index=True)

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
        num_epochs=CUSTOM_STAGE_EPOCHS,
        train_texts=train_df["text"].tolist(),
        train_labels=train_label_ids,
        eval_texts=eval_df["text"].tolist(),
        eval_labels=eval_label_ids,
        metadata={
            "source_dataset": str(resolve_dataset_path(DATASET_PATH).name),
            "custom_repeat_factor": CUSTOM_REPEAT_FACTOR,
            "train_label_distribution": _label_distribution(train_label_ids),
            "eval_label_distribution": _label_distribution(eval_label_ids),
            "data_report": data_report,
        },
    )
    return stage, test_df


def _build_class_weights(label_ids: list[int]) -> torch.Tensor:
    weights = np.ones(NUM_LABELS, dtype=np.float32)
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


def _build_training_args(stage: PreparedStage, stage_index: int) -> TrainingArguments:
    stage_output_dir = OUTPUT_DIR / f"stage_{stage_index + 1}_{stage.name}"
    return TrainingArguments(
        output_dir=str(stage_output_dir),
        overwrite_output_dir=True,
        num_train_epochs=stage.num_epochs,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
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
        seed=SEED,
    )


def _train_stage(model, tokenizer, stage: PreparedStage, stage_index: int) -> tuple[object, dict]:
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
    class_weights = _build_class_weights(stage.train_labels)

    trainer = WeightedTrainer(
        model=model,
        args=_build_training_args(stage, stage_index),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=compute_metrics,
        class_weights=class_weights,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    train_output = trainer.train()
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


def _evaluate_final_model(model, tokenizer, test_df: pd.DataFrame) -> tuple[dict, dict]:
    test_label_ids = _to_label_ids(test_df["emotion"].tolist())
    test_dataset = EmotionDataset(test_df["text"].tolist(), test_label_ids, tokenizer)

    trainer = Trainer(model=model)
    predictions = trainer.predict(test_dataset)
    predicted_ids = np.argmax(predictions.predictions, axis=-1)
    label_order = list(range(NUM_LABELS))

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


def _build_stage_sequence() -> tuple[list[PreparedStage], pd.DataFrame | None]:
    stages: list[PreparedStage] = []
    custom_test_df: pd.DataFrame | None = None

    if ENABLE_GOEMOTIONS:
        go_stage = prepare_goemotions_stage()
        if go_stage is not None:
            stages.append(go_stage)

    if ENABLE_DAIR_EMOTION:
        dair_stage = prepare_dair_stage()
        if dair_stage is not None:
            stages.append(dair_stage)

    if ENABLE_CUSTOM_FINAL_STAGE:
        custom_stage, custom_test_df = prepare_custom_stage()
        if custom_stage is not None:
            stages.append(custom_stage)

    return stages, custom_test_df


def train():
    print("=" * 60)
    print("EmoTune Staged BERT Fine-Tuning")
    print("=" * 60)
    print(
        f"Config: model={MODEL_NAME}, batch_size={BATCH_SIZE}, max_length={MAX_LENGTH}, "
        f"learning_rate={LEARNING_RATE}, max_per_class={MAX_SAMPLES_PER_CLASS}"
    )
    print(
        "Stage toggles: "
        f"goemotions={ENABLE_GOEMOTIONS}, "
        f"dair_ai_emotion={ENABLE_DAIR_EMOTION}, "
        f"emotune_final={ENABLE_CUSTOM_FINAL_STAGE}"
    )

    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)

    stages, custom_test_df = _build_stage_sequence()
    if not stages:
        raise RuntimeError("No training stages were prepared. Check dataset availability and stage toggles.")

    print("\nStage order:")
    for index, stage in enumerate(stages, start=1):
        print(f"  {index}. {stage.description} ({stage.num_epochs} epochs)")

    print(f"\nLoading base model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=NUM_LABELS,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stage_summaries = []
    for index, stage in enumerate(stages):
        model, stage_summary = _train_stage(model, tokenizer, stage, index)
        stage_summaries.append(stage_summary)

    print("\nSaving final model...")
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    final_results = {}
    prediction_dump = {}
    if custom_test_df is not None and not custom_test_df.empty:
        final_results, prediction_dump = _evaluate_final_model(model, tokenizer, custom_test_df)
    else:
        print("\nSkipping final EmoTune evaluation because no custom test split was available.")

    results_payload = {
        "seed": SEED,
        "model_name": MODEL_NAME,
        "stage_sequence": [summary["stage"] for summary in stage_summaries],
        "stage_summaries": stage_summaries,
        "final_results": final_results,
        "config": {
            "batch_size": BATCH_SIZE,
            "max_length": MAX_LENGTH,
            "learning_rate": LEARNING_RATE,
            "warmup_ratio": WARMUP_RATIO,
            "max_samples_per_class": MAX_SAMPLES_PER_CLASS,
            "custom_repeat_factor": CUSTOM_REPEAT_FACTOR,
            "enable_goemotions": ENABLE_GOEMOTIONS,
            "enable_dair_emotion": ENABLE_DAIR_EMOTION,
            "enable_custom_final_stage": ENABLE_CUSTOM_FINAL_STAGE,
            "goemotions_stage_epochs": GOEMOTIONS_STAGE_EPOCHS,
            "dair_stage_epochs": DAIR_STAGE_EPOCHS,
            "custom_stage_epochs": CUSTOM_STAGE_EPOCHS,
        },
    }

    with open(OUTPUT_DIR / "training_results.json", "w", encoding="utf-8") as handle:
        json.dump(results_payload, handle, indent=2)

    if prediction_dump:
        with open(OUTPUT_DIR / "test_predictions.json", "w", encoding="utf-8") as handle:
            json.dump(prediction_dump, handle, indent=2)

    print(f"\nFinal model saved to: {OUTPUT_DIR}")
    if final_results:
        print(f"EmoTune Test Accuracy: {final_results['test_accuracy']:.4f}")
        print(f"EmoTune Weighted F1: {final_results['weighted_f1']:.4f}")
    print("\nTraining complete!")


if __name__ == "__main__":
    train()
