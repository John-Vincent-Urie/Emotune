"""Shared emotion label definitions, GoEmotions mapping, and HF loader helper.

Single source of truth for the runtime classifier (``backend/ml/emotion_classifier.py``)
and the BERT training pipeline (``ml_model/train_bert.py``), which both need to agree on
the label list/ids and the GoEmotions -> EmoTune label mapping. This module has no Django
dependency so it can be imported by the standalone training script.
"""
from __future__ import annotations

import warnings

EMOTIONS = [
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

LABEL2ID = {label: index for index, label in enumerate(EMOTIONS)}
ID2LABEL = {index: label for index, label in enumerate(EMOTIONS)}

# GoEmotions label -> EmoTune label. Verified identical between the previous
# copies in ml_model/train_bert.py (GOEMOTIONS_MAP) and
# backend/ml/emotion_classifier.py (GOEMOTIONS_LABEL_MAP) before merging.
GOEMOTIONS_LABEL_MAP = {
    'admiration': 'happy',
    'amusement': 'happy',
    'anger': 'angry',
    'annoyance': 'angry',
    'approval': 'happy',
    'boredom': 'mixed',
    'caring': 'romantic',
    'confusion': 'mixed',
    'curiosity': 'surprising',
    'desire': 'romantic',
    'disappointment': 'sad',
    'disapproval': 'angry',
    'disgust': 'angry',
    'embarrassment': 'sad',
    'excitement': 'happy',
    'fear': 'fear',
    'gratitude': 'happy',
    'grief': 'sad',
    'joy': 'happy',
    'love': 'romantic',
    'neutral': 'calm',
    'nervousness': 'fear',
    'optimism': 'motivational',
    'pride': 'motivational',
    'realization': 'surprising',
    'relief': 'calm',
    'remorse': 'sad',
    'sadness': 'sad',
    'surprise': 'surprising',
}

HF_RESUME_DOWNLOAD_WARNING = (
    r"`resume_download` is deprecated and will be removed in version 1\.0\.0\."
)


def call_huggingface_loader(loader, *args, **kwargs):
    """Suppress an upstream deprecation warning emitted by older transformers releases."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=HF_RESUME_DOWNLOAD_WARNING,
            category=FutureWarning,
            module="huggingface_hub.file_download",
        )
        return loader(*args, **kwargs)
