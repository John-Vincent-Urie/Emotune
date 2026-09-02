"""Utilities for dataset cleaning, validation, and baseline experiments."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = Path(__file__).resolve().parent / 'artifacts'

SUPPORTED_EMOTIONS = [
    'happy',
    'sad',
    'angry',
    'motivational',
    'fear',
    'depressing',
    'surprising',
    'stressed',
    'calm',
    'lonely',
    'romantic',
    'nostalgic',
    'mixed',
]

RECOMMENDED_REDUCED_LABEL_MAP = {
    'happy': 'happy',
    'sad': 'sad',
    'angry': 'angry',
    'motivational': 'motivational',
    'fear': 'fear_or_anxious',
    'depressing': 'sad',
    'surprising': 'neutral_or_mixed',
    'stressed': 'stressed',
    'calm': 'calm',
    'lonely': 'neutral_or_mixed',
    'romantic': 'romantic',
    'nostalgic': 'neutral_or_mixed',
    'mixed': 'neutral_or_mixed',
}


def resolve_dataset_path(path: Path | str | None = None) -> Path:
    raw_path = str(path or os.getenv('EMOTUNE_DATASET_PATH', '')).strip()
    if not raw_path:
        return PROJECT_ROOT / 'dataset' / 'emotune_custom_dataset.csv'

    dataset_path = Path(raw_path).expanduser()
    if dataset_path.is_absolute():
        return dataset_path
    return (PROJECT_ROOT / dataset_path).resolve()


def load_custom_dataset(path: Path | None = None) -> pd.DataFrame:
    dataset_path = resolve_dataset_path(path)
    return pd.read_csv(dataset_path)


def __getattr__(name: str):
    # Resolve DATASET_PATH lazily on first access (PEP 562) instead of at import
    # time, so importing this module has no env-var side effect on its own and
    # `EMOTUNE_DATASET_PATH` is always read fresh.
    if name == 'DATASET_PATH':
        return resolve_dataset_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _normalize_text_and_emotion_columns(working: pd.DataFrame) -> pd.DataFrame:
    working['text'] = working['text'].fillna('').astype(str).str.strip()
    working['emotion'] = working['emotion'].fillna('').astype(str).str.strip().str.lower()
    return working


def _filter_empty_rows(working: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    empty_text_rows = int((working['text'] == '').sum())
    empty_label_rows = int((working['emotion'] == '').sum())
    working = working[(working['text'] != '') & (working['emotion'] != '')]
    return working, empty_text_rows, empty_label_rows


def _filter_invalid_labels(working: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    invalid_label_rows = int((~working['emotion'].isin(SUPPORTED_EMOTIONS)).sum())
    working = working[working['emotion'].isin(SUPPORTED_EMOTIONS)].copy()
    return working, invalid_label_rows


def _deduplicate(working: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    working['normalized_text'] = (
        working['text']
        .str.lower()
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
    )
    duplicate_rows = int(
        working.duplicated(subset=['normalized_text', 'emotion']).sum()
    )
    working = working.drop_duplicates(subset=['normalized_text', 'emotion']).copy()
    return working, duplicate_rows


def _add_derived_columns(working: pd.DataFrame) -> pd.DataFrame:
    working['text_length_chars'] = working['text'].str.len()
    working['text_length_words'] = working['normalized_text'].str.split().str.len()
    working['recommended_label'] = working['emotion'].map(RECOMMENDED_REDUCED_LABEL_MAP)
    return working


def _build_cleaning_report(
    working: pd.DataFrame,
    *,
    original_count: int,
    empty_text_rows: int,
    empty_label_rows: int,
    invalid_label_rows: int,
    duplicate_rows: int,
) -> dict:
    return {
        'rows_original': original_count,
        'rows_after_cleaning': int(len(working)),
        'rows_removed': int(original_count - len(working)),
        'empty_text_rows_removed': empty_text_rows,
        'empty_label_rows_removed': empty_label_rows,
        'invalid_label_rows_removed': invalid_label_rows,
        'duplicate_rows_removed': duplicate_rows,
        'label_distribution': {
            label: int(count)
            for label, count in working['emotion'].value_counts().sort_index().items()
        },
        'recommended_reduced_distribution': {
            label: int(count)
            for label, count in working['recommended_label'].value_counts().sort_index().items()
        },
        'text_length_summary': {
            'chars_mean': round(float(working['text_length_chars'].mean()), 2) if not working.empty else 0.0,
            'chars_median': round(float(working['text_length_chars'].median()), 2) if not working.empty else 0.0,
            'words_mean': round(float(working['text_length_words'].mean()), 2) if not working.empty else 0.0,
            'words_median': round(float(working['text_length_words'].median()), 2) if not working.empty else 0.0,
        },
    }


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    original_count = len(df)
    working = df.copy()

    if 'text' not in working.columns or 'emotion' not in working.columns:
        raise ValueError("Dataset must contain 'text' and 'emotion' columns.")

    working = _normalize_text_and_emotion_columns(working)
    working, empty_text_rows, empty_label_rows = _filter_empty_rows(working)
    working, invalid_label_rows = _filter_invalid_labels(working)
    working, duplicate_rows = _deduplicate(working)
    working = _add_derived_columns(working)

    report = _build_cleaning_report(
        working,
        original_count=original_count,
        empty_text_rows=empty_text_rows,
        empty_label_rows=empty_label_rows,
        invalid_label_rows=invalid_label_rows,
        duplicate_rows=duplicate_rows,
    )

    cleaned = working.drop(columns=['normalized_text']).reset_index(drop=True)
    return cleaned, report


def split_dataset(
    df: pd.DataFrame,
    *,
    test_size: float = 0.2,
    validation_size: float = 0.1,
    random_state: int = 42,
):
    if df.empty:
        raise ValueError('Cannot split an empty dataset.')

    holdout_size = test_size + validation_size
    if holdout_size <= 0 or holdout_size >= 1:
        raise ValueError('validation_size + test_size must be between 0 and 1.')

    train_df, temp_df = train_test_split(
        df,
        test_size=holdout_size,
        random_state=random_state,
        stratify=df['emotion'],
    )
    validation_ratio = validation_size / holdout_size
    validation_df, test_df = train_test_split(
        temp_df,
        test_size=1 - validation_ratio,
        random_state=random_state,
        stratify=temp_df['emotion'],
    )
    return train_df.reset_index(drop=True), validation_df.reset_index(drop=True), test_df.reset_index(drop=True)


def ensure_artifacts_dir() -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
