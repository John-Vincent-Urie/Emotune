"""
Export EmoTune music-picker training examples from production-style history.

This creates an SFT-friendly JSONL file from prompt history records that contain
candidate tracks plus the final selected track.
"""
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'backend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emotune_project.settings')

import django  # noqa: E402

django.setup()  # noqa: E402

from django.db.utils import OperationalError  # noqa: E402
from users.models import PromptHistory  # noqa: E402


ARTIFACT_DIR = REPO_ROOT / 'ml_model' / 'artifacts'
OUTPUT_PATH = ARTIFACT_DIR / 'music_picker_training.jsonl'


def _extract_picker_data(history) -> dict:
    return history.music_picker_data if isinstance(history.music_picker_data, dict) else {}


def _serialize_candidate(candidate: dict) -> dict:
    candidate_id = str(candidate.get('id') or candidate.get('uri') or '').strip()
    return {
        'candidate_id': candidate_id,
        'name': candidate.get('name'),
        'artist': candidate.get('artist'),
        'album': candidate.get('album'),
        'popularity': candidate.get('popularity'),
        'recommendation_source': candidate.get('recommendation_source'),
        'selection_reasons': candidate.get('selection_reasons', []),
        'emotion_alignment_score': candidate.get('emotion_alignment_score'),
        'emotion_alignment_reasons': candidate.get('emotion_alignment_reasons', []),
        'personalization_score': candidate.get('personalization_score'),
        'is_preferred': bool(candidate.get('is_preferred')),
    }


def _serialize_candidates(candidates, selected_track_id: str) -> tuple[list[dict], dict | None]:
    selected_track = None
    serialized_candidates = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        serialized_candidate = _serialize_candidate(candidate)
        serialized_candidates.append(serialized_candidate)
        if serialized_candidate['candidate_id'] == selected_track_id:
            selected_track = serialized_candidate
    return serialized_candidates, selected_track


def _build_prompt_answer_pair(
    history,
    picker_data: dict,
    serialized_candidates: list[dict],
    selected_track_id: str,
    playlist_track_ids: list[str],
) -> dict:
    prompt = {
        'prompt_text': history.prompt_text,
        'emotion': history.detected_emotion,
        'confidence_band': picker_data.get('confidence_band'),
        'emotion_scores': history.emotion_scores,
        'candidates': serialized_candidates,
    }
    answer = {
        'selected_candidate_id': selected_track_id,
        'playlist_candidate_ids': playlist_track_ids or [selected_track_id],
        'reason': picker_data.get('reason') or 'Selected from prior EmoTune interaction.',
    }
    return {
        'messages': [
            {
                'role': 'system',
                'content': (
                    "You are EmoTune's music picker. Choose the candidate tracks that best "
                    "match the user's emotional context. Treat emotion_alignment_score as a "
                    "strong prior and avoid candidates that conflict with the target vibe."
                ),
            },
            {'role': 'user', 'content': json.dumps(prompt, ensure_ascii=True)},
            {'role': 'assistant', 'content': json.dumps(answer, ensure_ascii=True)},
        ],
        'metadata': {
            'prompt_history_id': history.id,
            'strategy': picker_data.get('strategy'),
            'used_fallback': picker_data.get('used_fallback'),
            'selected_track_id': selected_track_id,
            'playlist_track_ids': playlist_track_ids or [selected_track_id],
            'felt_better_response': history.felt_better_response,
            'session_duration': history.session_duration,
        },
    }


def build_example(history, picker_data: dict | None = None):
    if picker_data is None:
        picker_data = _extract_picker_data(history)
    candidates = picker_data.get('candidate_tracks') or history.playlist_data or []
    selected_track_id = str(picker_data.get('selected_track_id') or '').strip()
    playlist_track_ids = [
        str(value or '').strip()
        for value in (picker_data.get('playlist_track_ids') or [])
        if str(value or '').strip()
    ]
    if not candidates or not selected_track_id:
        return None

    serialized_candidates, selected_track = _serialize_candidates(candidates, selected_track_id)
    if not serialized_candidates or not selected_track:
        return None

    return _build_prompt_answer_pair(
        history, picker_data, serialized_candidates, selected_track_id, playlist_track_ids
    )


def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        histories = PromptHistory.objects.order_by('id')
        written = 0
        with OUTPUT_PATH.open('w', encoding='utf-8') as handle:
            for history in histories.iterator():
                picker_data = _extract_picker_data(history)
                if not picker_data:
                    continue
                example = build_example(history, picker_data)
                if not example:
                    continue
                handle.write(json.dumps(example, ensure_ascii=True) + '\n')
                written += 1
    except OperationalError:
        print(
            'Database schema is not up to date for music picker export. '
            'Run `python manage.py migrate` first.'
        )
        return
    print(f'Wrote {written} examples to {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
