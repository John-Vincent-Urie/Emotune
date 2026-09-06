import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)
_warmup_started = False


def _warm_models():
    from .emotion_classifier import get_classifier

    try:
        classifier = get_classifier()
        classifier.warm_up(include_semantic_fallback=True)
        logger.info("Emotion models warmed up in the background.")
    except Exception:
        logger.exception("Emotion model warm-up failed.")


class MlConfig(AppConfig):
    name = 'ml'

    def ready(self):
        global _warmup_started

        if _warmup_started:
            return

        warmup_setting = str(
            os.getenv('EMOTUNE_WARM_MODELS_ON_STARTUP', 'true')
        ).strip().lower()
        if warmup_setting in {'0', 'false', 'no', 'off'}:
            return

        argv = {str(arg or '').strip().lower() for arg in sys.argv}
        is_runserver = 'runserver' in argv
        if is_runserver and os.getenv('RUN_MAIN') != 'true':
            return
        if not is_runserver and warmup_setting != 'always':
            return

        _warmup_started = True
        threading.Thread(
            target=_warm_models,
            name='emotune-model-warmup',
            daemon=True,
        ).start()
