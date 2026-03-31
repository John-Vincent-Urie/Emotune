"""
EmoTune emotion classifier.

The production path uses a fine-tuned BERT classifier when a saved model is
available. A deterministic keyword-based fallback remains available for local
development, model failures, and low-confidence predictions.
"""
import os
import random
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .plutchik_mapper import build_plutchik_profile

logger = logging.getLogger(__name__)

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

EMOTION_RESPONSES = {
    'happy': [
        "That is wonderful. Here are some upbeat tracks to keep the good vibes going.",
        "Love that energy. Let's celebrate it with some feel-good music.",
    ],
    'sad': [
        "It is okay to feel sad. Here are some songs for a gentler moment.",
        "You are not alone. These tracks are here to sit with you.",
    ],
    'angry': [
        "I hear the intensity in that. Here is music to help channel it.",
        "Take a breath. These tracks might help you process that energy.",
    ],
    'motivational': [
        "You have this. Here are some tracks to keep that momentum going.",
        "That sounds driven. Here is music to help you push forward.",
    ],
    'fear': [
        "It is okay to feel afraid. Here is something calmer to accompany you.",
        "That sounds heavy. Let this music help make the moment feel steadier.",
    ],
    'depressing': [
        "I am sorry this feels so heavy. Here is music for a quieter space.",
        "That sounds difficult. Let these tracks be gentle company for now.",
    ],
    'surprising': [
        "That sounds unexpected. Here is an eclectic mix to match the moment.",
        "What a surprise. These tracks might fit that energy.",
    ],
    'stressed': [
        "Take a breath. Here are calming tracks to help you slow things down.",
        "That sounds overwhelming. This music may help you reset a bit.",
    ],
    'calm': [
        "What a peaceful moment. Here are some serene tracks to match it.",
        "That sounds grounded. Here is music to stay in that calm space.",
    ],
    'lonely': [
        "Even when things feel quiet, music can still be company. Here are some tracks.",
        "That sounds lonely. These songs may feel like a little company.",
    ],
    'romantic': [
        "Love is in the air. Here are some romantic melodies for that feeling.",
        "That sounds warm and close. Here are songs to match it.",
    ],
    'nostalgic': [
        "There is something special about looking back. Here are songs for that mood.",
        "That sounds nostalgic. These tracks might fit those memories.",
    ],
    'mixed': [
        "Sometimes feelings are layered. Here is a mix that can hold more than one mood.",
        "That sounds complex. Here is music for a more mixed emotional space.",
    ],
}

FEEL_BETTER_RESPONSES = [
    "Feel better? Here is one more song to lift the mood a little more.",
    "You have been listening for a while. Here is an uplifting pick for you.",
    "I hope the music helped. Here is one more track just for you.",
]

EMOTION_KEYWORDS = {
    'happy': [
        'happy', 'joy', 'excited', 'great', 'wonderful', 'amazing',
        'fantastic', 'awesome', 'good', 'love', 'celebrate', 'cheerful',
        'elated', 'delighted', 'glad', 'thrilled',
    ],
    'sad': [
        'sad', 'cry', 'crying', 'tears', 'unhappy', 'miserable',
        'heartbroken', 'hurt', 'pain', 'sorrow', 'grief', 'miss', 'loss',
        'broken', 'weep',
    ],
    'angry': [
        'angry', 'anger', 'mad', 'furious', 'rage', 'frustrated',
        'irritated', 'annoyed', 'hate', 'upset', 'outraged', 'infuriated',
        'livid',
    ],
    'motivational': [
        'motivated', 'inspire', 'goal', 'achieve', 'success', 'hustle',
        'grind', 'dream', 'push', 'determination', 'ambition', 'power',
        'strength', 'conquer',
    ],
    'fear': [
        'scared', 'afraid', 'fear', 'nervous', 'anxious', 'terrified',
        'worried', 'panic', 'dread', 'frightened', 'phobia', 'paranoid',
    ],
    'depressing': [
        'depressed', 'depression', 'hopeless', 'worthless', 'empty', 'numb',
        'dark', 'bleak', 'despair', 'suicidal', 'meaningless', 'pointless',
    ],
    'surprising': [
        'surprised', 'shock', 'unexpected', 'amazed', 'astonished', 'wow',
        'unbelievable', 'incredible', 'mind-blown', 'stunned',
    ],
    'stressed': [
        'stressed', 'stress', 'overwhelmed', 'pressure', 'deadline', 'busy',
        'exhausted', 'tired', 'burnout', 'overloaded', 'tense', 'anxious',
    ],
    'calm': [
        'calm', 'peaceful', 'relaxed', 'serene', 'tranquil', 'zen',
        'content', 'quiet', 'still', 'meditative', 'composed', 'rest',
    ],
    'lonely': [
        'lonely', 'alone', 'isolated', 'abandoned', 'rejected', 'left out',
        'solitary', 'missing', 'longing', 'nobody', 'empty',
    ],
    'romantic': [
        'love', 'romance', 'romantic', 'crush', 'date', 'relationship',
        'affection', 'passion', 'intimate', 'adore', 'cherish', 'heart',
    ],
    'nostalgic': [
        'nostalgic', 'nostalgia', 'memories', 'remember', 'past', 'childhood',
        'miss', 'throwback', 'reminisce', 'old times', 'used to',
    ],
}

HEARTBREAK_PATTERNS = (
    re.compile(r'\bheart[\s-]?broken\b'),
    re.compile(r'\bbroken[\s-]?heart\b'),
    re.compile(r'\bheartbreak(?:ing)?\b'),
    re.compile(r'\bheart\s+is\s+broken\b'),
    re.compile(r'\bheart\s+has\s+been\s+broken\b'),
    re.compile(r'\bbroke\s+my\s+heart\b'),
    re.compile(r'\bbreak(?:ing)?\s+my\s+heart\b'),
)

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

DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.68
DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD = 0.45
DEFAULT_MIN_MARGIN_THRESHOLD = 0.12
DEFAULT_TOP_EMOTIONS = 2
DEFAULT_GOEMOTIONS_MODEL_ID = 'SamLowe/roberta-base-go_emotions'
DEFAULT_GOEMOTIONS_CONFIDENCE_THRESHOLD = 0.30
DEFAULT_GOEMOTIONS_MARGIN_THRESHOLD = 0.05


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class EmotionClassifier:
    """Hybrid classifier with BERT-first prediction and confidence fallback."""

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.model_loaded = False
        self.model_label_map = list(EMOTIONS)
        self.goemotions_model = None
        self.goemotions_tokenizer = None
        self.goemotions_model_loaded = False
        self.goemotions_label_map = []
        self.goemotions_enabled = False
        self.goemotions_model_id = DEFAULT_GOEMOTIONS_MODEL_ID
        self.goemotions_local_only = True
        self.goemotions_confidence_threshold = (
            DEFAULT_GOEMOTIONS_CONFIDENCE_THRESHOLD
        )
        self.goemotions_margin_threshold = DEFAULT_GOEMOTIONS_MARGIN_THRESHOLD
        self.high_confidence_threshold = DEFAULT_HIGH_CONFIDENCE_THRESHOLD
        self.medium_confidence_threshold = DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD
        self.min_margin_threshold = DEFAULT_MIN_MARGIN_THRESHOLD
        self.top_emotions_count = DEFAULT_TOP_EMOTIONS
        self._load_runtime_config()
        self._load_model()
        self._load_goemotions_model()

    def _load_runtime_config(self):
        try:
            from django.conf import settings
        except Exception:
            return

        self.high_confidence_threshold = _safe_float(
            getattr(settings, 'EMOTION_HIGH_CONFIDENCE_THRESHOLD', None),
            DEFAULT_HIGH_CONFIDENCE_THRESHOLD,
        )
        self.medium_confidence_threshold = _safe_float(
            getattr(settings, 'EMOTION_MEDIUM_CONFIDENCE_THRESHOLD', None),
            DEFAULT_MEDIUM_CONFIDENCE_THRESHOLD,
        )
        self.min_margin_threshold = _safe_float(
            getattr(settings, 'EMOTION_MIN_MARGIN_THRESHOLD', None),
            DEFAULT_MIN_MARGIN_THRESHOLD,
        )
        self.top_emotions_count = max(
            2,
            _safe_int(
                getattr(settings, 'EMOTION_TOP_EMOTIONS_COUNT', None),
                DEFAULT_TOP_EMOTIONS,
            ),
        )
        self.goemotions_enabled = bool(
            getattr(settings, 'EMOTION_GOEMOTIONS_ENABLED', False)
        )
        self.goemotions_model_id = (
            str(
                getattr(
                    settings,
                    'EMOTION_GOEMOTIONS_MODEL_ID',
                    DEFAULT_GOEMOTIONS_MODEL_ID,
                )
                or DEFAULT_GOEMOTIONS_MODEL_ID
            )
            .strip()
            or DEFAULT_GOEMOTIONS_MODEL_ID
        )
        self.goemotions_local_only = bool(
            getattr(settings, 'EMOTION_GOEMOTIONS_LOCAL_ONLY', True)
        )
        self.goemotions_confidence_threshold = _safe_float(
            getattr(
                settings,
                'EMOTION_GOEMOTIONS_MIN_CONFIDENCE_THRESHOLD',
                None,
            ),
            DEFAULT_GOEMOTIONS_CONFIDENCE_THRESHOLD,
        )
        self.goemotions_margin_threshold = _safe_float(
            getattr(
                settings,
                'EMOTION_GOEMOTIONS_MIN_MARGIN_THRESHOLD',
                None,
            ),
            DEFAULT_GOEMOTIONS_MARGIN_THRESHOLD,
        )

    def _load_model(self):
        """Load the saved BERT model if one is available."""
        try:
            from django.conf import settings

            model_source, is_local = self._resolve_model_source(getattr(settings, 'ML_MODEL_PATH', ''))
            if not model_source:
                logger.warning("No emotion model source configured. Using keyword fallback.")
                return

            if is_local:
                config_path = Path(model_source) / 'config.json'
                if not config_path.exists():
                    logger.warning(
                        "Emotion model directory %s is missing config.json. Using keyword fallback.",
                        model_source,
                    )
                    return

            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            self.tokenizer = AutoTokenizer.from_pretrained(str(model_source))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_source))
            label_map = self._resolve_model_label_map(self.model)
            if not label_map:
                logger.warning(
                    "Emotion model labels do not match EmoTune emotions. Using keyword fallback."
                )
                self.model = None
                self.tokenizer = None
                return

            self.model_label_map = label_map
            self.model.eval()
            self.model_loaded = True
            logger.info("Loaded BERT emotion model from %s", model_source)
        except Exception as error:
            logger.warning("Could not load BERT model: %s. Using keyword fallback.", error)

    def _load_goemotions_model(self):
        """Load the GoEmotions model used for semantic fallback decisions."""
        if not self.goemotions_enabled:
            return

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            self.goemotions_tokenizer = AutoTokenizer.from_pretrained(
                self.goemotions_model_id,
                local_files_only=self.goemotions_local_only,
            )
            self.goemotions_model = AutoModelForSequenceClassification.from_pretrained(
                self.goemotions_model_id,
                local_files_only=self.goemotions_local_only,
            )
            label_map = self._resolve_goemotions_label_map(self.goemotions_model)
            if not label_map:
                logger.warning(
                    "GoEmotions model labels are unavailable or invalid. Disabling GoEmotions fallback."
                )
                self.goemotions_model = None
                self.goemotions_tokenizer = None
                return

            self.goemotions_label_map = label_map
            self.goemotions_model.eval()
            self.goemotions_model_loaded = True
            logger.info(
                "Loaded GoEmotions fallback model from %s",
                self.goemotions_model_id,
            )
        except Exception as error:
            logger.warning(
                "Could not load GoEmotions fallback model: %s. Continuing without it.",
                error,
            )

    def _resolve_model_source(self, configured_source):
        model_source = str(configured_source or '').strip()
        if not model_source:
            return None, False

        base_dir = None
        try:
            from django.conf import settings

            base_dir = Path(getattr(settings, 'BASE_DIR', ''))
        except Exception:
            base_dir = None

        candidate_path = Path(model_source).expanduser()
        if not candidate_path.is_absolute() and base_dir:
            candidate_path = (base_dir / candidate_path).resolve()

        if candidate_path.exists():
            return str(candidate_path), True

        if self._looks_like_local_model_path(model_source):
            logger.warning("Emotion model path %s not found. Using keyword fallback.", model_source)
            return None, False

        return model_source, False

    def _looks_like_local_model_path(self, value):
        normalized = str(value or '').strip()
        if not normalized:
            return False
        path_value = Path(normalized)
        return (
            path_value.is_absolute()
            or '\\' in normalized
            or normalized.startswith('.')
        )

    def _canonicalize_model_label(self, label):
        normalized = re.sub(r'[^a-z0-9]+', '_', str(label or '').strip().lower()).strip('_')
        return {
            'depressed': 'depressing',
        }.get(normalized, normalized)

    def _canonicalize_goemotions_label(self, label):
        return re.sub(
            r'[^a-z0-9]+',
            '_',
            str(label or '').strip().lower(),
        ).strip('_')

    def _resolve_model_label_map(self, model):
        config = getattr(model, 'config', None)
        if not config:
            return None

        expected_emotions = set(EMOTIONS)
        id2label = getattr(config, 'id2label', None)
        num_labels = _safe_int(getattr(config, 'num_labels', None), 0)

        if isinstance(id2label, dict) and id2label:
            ordered_labels = []
            for index in range(len(id2label)):
                raw_label = id2label.get(index, id2label.get(str(index)))
                canonical_label = self._canonicalize_model_label(raw_label)
                if not canonical_label:
                    return None
                ordered_labels.append(canonical_label)

            if len(ordered_labels) != len(EMOTIONS):
                return None

            if set(ordered_labels) == expected_emotions:
                return ordered_labels

            if all(label.startswith('label_') for label in ordered_labels):
                logger.warning(
                    "Emotion model uses generic label names. Assuming EmoTune label order."
                )
                return list(EMOTIONS)

            return None

        if num_labels == len(EMOTIONS):
            logger.warning(
                "Emotion model config is missing label names. Assuming EmoTune label order."
            )
            return list(EMOTIONS)

        return None

    def _resolve_goemotions_label_map(self, model):
        config = getattr(model, 'config', None)
        if not config:
            return None

        id2label = getattr(config, 'id2label', None)
        if not isinstance(id2label, dict) or not id2label:
            return None

        ordered_labels = []
        for index in range(len(id2label)):
            raw_label = id2label.get(index, id2label.get(str(index)))
            canonical_label = self._canonicalize_goemotions_label(raw_label)
            if not canonical_label or canonical_label.startswith('label_'):
                return None
            ordered_labels.append(canonical_label)
        return ordered_labels

    def predict(self, text: str) -> dict:
        """Predict emotion from text with confidence-based fallback handling."""
        raw_text = str(text or '').strip()
        normalized_text = raw_text.lower()
        if not normalized_text:
            return self._build_uncertain_result(fallback_reason='empty_text')

        if self.model_loaded:
            return self._bert_predict(raw_text, keyword_text=normalized_text)

        goemotions_result = self._goemotions_fallback_or_none(
            raw_text,
            prediction_strategy='goemotions_only',
            fallback_reason='model_not_loaded',
            fallback_used=False,
        )
        if goemotions_result is not None:
            return goemotions_result
        return self._keyword_predict(
            normalized_text,
            prediction_strategy='keyword_only',
            fallback_reason='model_not_loaded',
        )

    def _bert_predict(self, text: str, *, keyword_text: Optional[str] = None) -> dict:
        try:
            import torch

            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=128,
                padding=True,
            )
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1).squeeze().cpu().numpy()

            bert_scores = {
                self.model_label_map[index]: float(probs[index])
                for index in range(min(len(self.model_label_map), len(probs)))
            }
            ranking = self._rank_scores(bert_scores)
            top_prediction = ranking[0]
            confidence_margin = self._confidence_margin(ranking)

            if (
                top_prediction['confidence'] >= self.high_confidence_threshold
                and confidence_margin >= self.min_margin_threshold
            ):
                return self._build_result(
                    bert_scores,
                    prediction_source='bert',
                    prediction_strategy='bert_high_confidence',
                    fallback_used=False,
                    fallback_reason=None,
                    uncertain=False,
                )

            if top_prediction['confidence'] >= self.medium_confidence_threshold:
                return self._build_result(
                    bert_scores,
                    prediction_source='bert',
                    prediction_strategy='bert_medium_confidence',
                    fallback_used=False,
                    fallback_reason=None,
                    uncertain=True,
                )

            goemotions_result = self._goemotions_fallback_or_none(
                text,
                prediction_strategy='goemotions_low_confidence_fallback',
                fallback_reason='low_model_confidence',
                model_prediction=top_prediction,
            )
            if goemotions_result is not None:
                return goemotions_result

            keyword_result = self._keyword_predict(
                keyword_text or text.lower(),
                prediction_strategy='keyword_fallback',
                fallback_reason='low_model_confidence',
                model_prediction=top_prediction,
            )
            keyword_result['model_prediction'] = top_prediction
            return keyword_result
        except Exception as error:
            logger.error("BERT prediction failed: %s", error)
            goemotions_result = self._goemotions_fallback_or_none(
                text,
                prediction_strategy='goemotions_bert_error_fallback',
                fallback_reason='bert_prediction_error',
            )
            if goemotions_result is not None:
                return goemotions_result
            return self._keyword_predict(
                keyword_text or text.lower(),
                prediction_strategy='keyword_fallback',
                fallback_reason='bert_prediction_error',
            )

    def _goemotions_fallback_or_none(
        self,
        text: str,
        *,
        prediction_strategy: str,
        fallback_reason: Optional[str],
        fallback_used: bool = True,
        model_prediction: Optional[dict] = None,
    ) -> Optional[dict]:
        if not self.goemotions_model_loaded:
            return None

        result = self._goemotions_predict(
            text,
            prediction_strategy=prediction_strategy,
            fallback_reason=fallback_reason,
            fallback_used=fallback_used,
            model_prediction=model_prediction,
        )
        if result is None or not self._should_prefer_goemotions_result(result):
            return None
        return result

    def _goemotions_predict(
        self,
        text: str,
        *,
        prediction_strategy: str,
        fallback_reason: Optional[str],
        fallback_used: bool,
        model_prediction: Optional[dict] = None,
    ) -> Optional[dict]:
        if not self.goemotions_model_loaded:
            return None

        try:
            import torch

            inputs = self.goemotions_tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=128,
                padding=True,
            )
            with torch.no_grad():
                outputs = self.goemotions_model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1).squeeze().cpu().numpy()

            raw_scores = {
                self.goemotions_label_map[index]: float(probs[index])
                for index in range(
                    min(len(self.goemotions_label_map), len(probs))
                )
            }
            emotion_scores = self._aggregate_goemotions_scores(raw_scores)
            if not any(score > 0 for score in emotion_scores.values()):
                return None

            normalized_scores = self._normalize_scores(emotion_scores)
            ranking = self._rank_scores(normalized_scores)
            confidence_band = self._confidence_band(
                ranking[0]['confidence'],
                self._confidence_margin(ranking),
            )
            result = self._build_result(
                normalized_scores,
                prediction_source='goemotions',
                prediction_strategy=prediction_strategy,
                fallback_used=fallback_used,
                fallback_reason=(fallback_reason if fallback_used else None),
                uncertain=confidence_band != 'high',
            )
            if model_prediction:
                result['model_prediction'] = model_prediction
            return result
        except Exception as error:
            logger.warning("GoEmotions fallback prediction failed: %s", error)
            return None

    def _aggregate_goemotions_scores(
        self,
        scores: Dict[str, float],
    ) -> Dict[str, float]:
        aggregated_scores = {emotion: 0.0 for emotion in EMOTIONS}

        for label, value in scores.items():
            mapped_emotion = GOEMOTIONS_LABEL_MAP.get(
                self._canonicalize_goemotions_label(label)
            )
            if mapped_emotion in aggregated_scores:
                aggregated_scores[mapped_emotion] += max(0.0, float(value))

        return aggregated_scores

    def _should_prefer_goemotions_result(self, result: Optional[dict]) -> bool:
        if not isinstance(result, dict):
            return False

        top_emotion = str(result.get('emotion') or '').strip().lower()
        confidence = max(0.0, _safe_float(result.get('confidence'), 0.0))
        margin = max(0.0, _safe_float(result.get('confidence_margin'), 0.0))

        if not top_emotion or top_emotion == 'mixed':
            return False

        return (
            confidence >= self.goemotions_confidence_threshold
            or margin >= self.goemotions_margin_threshold
        )

    def _keyword_predict(
        self,
        text: str,
        *,
        prediction_strategy: str,
        fallback_reason: Optional[str],
        model_prediction: Optional[dict] = None,
    ) -> dict:
        scores = self._keyword_scores(text)
        if not any(score > 0 for score in scores.values()):
            return self._build_uncertain_result(
                prediction_source='keyword',
                prediction_strategy=prediction_strategy,
                fallback_reason=fallback_reason or 'no_keyword_match',
                model_prediction=model_prediction,
            )

        normalized_scores = self._normalize_scores(scores)
        result = self._build_result(
            normalized_scores,
            prediction_source='keyword',
            prediction_strategy=prediction_strategy,
            fallback_used=prediction_strategy != 'keyword_only',
            fallback_reason=fallback_reason,
            uncertain=True,
        )
        if model_prediction:
            result['model_prediction'] = model_prediction
        return result

    def _keyword_scores(self, text: str) -> Dict[str, float]:
        collapsed_text = re.sub(r'\s+', ' ', str(text).lower()).strip()
        normalized_text = f" {collapsed_text} "
        scores = {emotion: 0.0 for emotion in EMOTIONS}

        for emotion, keywords in EMOTION_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                normalized_keyword = str(keyword or '').strip().lower()
                if not normalized_keyword:
                    continue
                if ' ' in normalized_keyword:
                    count = normalized_text.count(f" {normalized_keyword} ")
                else:
                    count = len(
                        re.findall(
                            rf'\b{re.escape(normalized_keyword)}\b',
                            normalized_text,
                        )
                    )
                score += float(count)
            scores[emotion] = score
        return self._apply_contextual_keyword_adjustments(collapsed_text, scores)

    def _apply_contextual_keyword_adjustments(
        self,
        text: str,
        scores: Dict[str, float],
    ) -> Dict[str, float]:
        adjusted_scores = dict(scores)

        if any(pattern.search(text) for pattern in HEARTBREAK_PATTERNS):
            adjusted_scores['sad'] += 2.0
            adjusted_scores['romantic'] = max(
                0.0,
                adjusted_scores['romantic'] - 0.75,
            )

        return adjusted_scores

    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        sanitized = {emotion: max(0.0, float(scores.get(emotion, 0.0))) for emotion in EMOTIONS}
        total = sum(sanitized.values())
        if total <= 0:
            return self._build_uncertain_distribution()
        return {emotion: value / total for emotion, value in sanitized.items()}

    def _build_uncertain_distribution(self) -> Dict[str, float]:
        other_weight = 0.65 / max(len(EMOTIONS) - 1, 1)
        distribution = {emotion: other_weight for emotion in EMOTIONS}
        distribution['mixed'] = 0.35
        return distribution

    def _rank_scores(self, scores: Dict[str, float]) -> List[dict]:
        ranking = [
            {'emotion': emotion, 'confidence': float(scores.get(emotion, 0.0))}
            for emotion in EMOTIONS
        ]
        ranking.sort(key=lambda item: (-item['confidence'], item['emotion']))
        return ranking

    def _confidence_margin(self, ranking: List[dict]) -> float:
        if len(ranking) < 2:
            return ranking[0]['confidence'] if ranking else 0.0
        return max(0.0, ranking[0]['confidence'] - ranking[1]['confidence'])

    def _confidence_band(self, confidence: float, margin: float) -> str:
        if confidence >= self.high_confidence_threshold and margin >= self.min_margin_threshold:
            return 'high'
        if confidence >= self.medium_confidence_threshold:
            return 'medium'
        return 'low'

    def _build_result(
        self,
        scores: Dict[str, float],
        *,
        prediction_source: str,
        prediction_strategy: str,
        fallback_used: bool,
        fallback_reason: Optional[str],
        uncertain: bool,
    ) -> dict:
        ranking = self._rank_scores(scores)
        top_prediction = ranking[0]
        confidence_margin = self._confidence_margin(ranking)
        confidence_band = self._confidence_band(
            top_prediction['confidence'],
            confidence_margin,
        )
        top_emotions = ranking[:self.top_emotions_count]
        secondary_emotion = top_emotions[1]['emotion'] if len(top_emotions) > 1 else None
        plutchik_profile = build_plutchik_profile(scores)

        return {
            'emotion': top_prediction['emotion'],
            'confidence': top_prediction['confidence'],
            'all_scores': scores,
            'top_emotions': top_emotions,
            'secondary_emotion': secondary_emotion,
            'plutchik_scores': plutchik_profile['plutchik_scores'],
            'plutchik_top_emotions': plutchik_profile['plutchik_top_emotions'],
            'plutchik_dominant_emotion': plutchik_profile['plutchik_dominant_emotion'],
            'plutchik_profile_version': plutchik_profile['plutchik_profile_version'],
            'prediction_source': prediction_source,
            'prediction_strategy': prediction_strategy,
            'confidence_band': confidence_band,
            'confidence_margin': confidence_margin,
            'fallback_used': bool(fallback_used),
            'fallback_reason': fallback_reason,
            'needs_review': bool(uncertain or confidence_band != 'high'),
            'label_schema_version': 'v1',
        }

    def _build_uncertain_result(
        self,
        *,
        prediction_source: str = 'system',
        prediction_strategy: str = 'system_fallback',
        fallback_reason: Optional[str] = 'uncertain_input',
        model_prediction: Optional[dict] = None,
    ) -> dict:
        distribution = self._build_uncertain_distribution()
        result = self._build_result(
            distribution,
            prediction_source=prediction_source,
            prediction_strategy=prediction_strategy,
            fallback_used=True,
            fallback_reason=fallback_reason,
            uncertain=True,
        )
        if model_prediction:
            result['model_prediction'] = model_prediction
        return result


_classifier = None


def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = EmotionClassifier()
    return _classifier


def get_ai_response(emotion: str) -> str:
    responses = EMOTION_RESPONSES.get(emotion, EMOTION_RESPONSES['mixed'])
    return random.choice(responses)


def get_feel_better_message() -> str:
    return random.choice(FEEL_BETTER_RESPONSES)
