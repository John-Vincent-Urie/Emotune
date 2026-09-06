#!/usr/bin/env python3
"""
Fit the EmoTune music picker's ranking weights from real picks.

The picker scores candidates as a weighted sum of features (see
api/picker_ranker.py). Those weights shipped hand-tuned; this script learns
them instead, from what the picker actually chose and what users actually
listened to.

Training data is one row per candidate, grouped by prompt. What counts as the
positive depends on --label:

  outcome    (default) the candidate the user actually listened through. This
             is the only label that carries information the picker does not
             already have, so it is the one worth training on.
  selection  the candidate the picker chose. MEASURED AS DEGENERATE on this
             database: the pick was candidate #0 in 164 of 167 prompts, because
             the stored candidate list is already in ranked order. Training on
             it is a feedback loop -- the model relearns the ranking that
             produced the label and reports a perfect score for doing nothing.
             Kept only so that leakage stays visible and measurable.

Splitting is by prompt, never by row: candidates from one prompt must not land
on both sides of the split, or the score is inflated by leakage.

The artifact is only written if the fitted weights beat the current defaults on
held-out prompts. A model that cannot win does not deserve to ship.

Usage (no venv activation needed -- see ml_model/_bootstrap.py):
    python3 ml_model/train_picker_ranker.py
    python3 ml_model/train_picker_ranker.py --dry-run
    python3 ml_model/train_picker_ranker.py --label selection
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import (  # noqa: E402
    REPO_ROOT,
    add_backend_to_path,
    ensure_local_venv,
)

ensure_local_venv('django')
add_backend_to_path()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emotune_project.settings')

import django  # noqa: E402

django.setup()  # noqa: E402

import numpy as np  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from api.picker_ranker import (  # noqa: E402
    DEFAULT_BIAS,
    DEFAULT_WEIGHTS,
    FEATURE_ORDER,
    build_feature_rows,
)
from users.models import FavoriteTrack, ListeningSession, PromptHistory  # noqa: E402

ARTIFACT_PATH = REPO_ROOT / 'ml_model' / 'artifacts' / 'picker_weights.json'

# Below this many usable prompts the fit is memorizing, not learning.
MIN_PROMPTS = 60
# Held-out share, by prompt.
TEST_FRACTION = 0.25
# Outcome weighting for a positive whose listen actually went well.
COMPLETED_LISTEN_WEIGHT = 2.0
FELT_BETTER_WEIGHT = 1.5
FAVORITED_WEIGHT = 2.5


def _picker_data(history):
    return history.music_picker_data if isinstance(history.music_picker_data, dict) else {}


def _allows_learning(history):
    personalization = _picker_data(history).get('personalization')
    return not (isinstance(personalization, dict) and personalization.get('train_session') is False)


def _positive_weight(history, track_id, completed_track_ids, favorite_track_ids):
    """How much this pick counts. A pick is evidence; a pick that was played
    through, or that the user said helped, is better evidence."""
    weight = 1.0
    if track_id in completed_track_ids:
        weight *= COMPLETED_LISTEN_WEIGHT
    if track_id in favorite_track_ids:
        weight *= FAVORITED_WEIGHT
    if history.felt_better_response is True:
        weight *= FELT_BETTER_WEIGHT
    return weight


# A listen this far into a track is a positive even if it was never flagged
# complete; anything shorter is not evidence the pick landed.
LISTENED_THROUGH_RATIO = 0.6


def _listened_track_ids(history_id, sessions_by_history, candidates_by_id):
    """Track ids from this prompt the user genuinely stayed with."""
    listened = set()
    for track_id, duration, completed in sessions_by_history.get(history_id, []):
        if completed:
            listened.add(track_id)
            continue
        track = candidates_by_id.get(track_id) or {}
        full_length_ms = float(track.get('duration_ms') or 0)
        if full_length_ms > 0 and duration >= (full_length_ms / 1000.0) * LISTENED_THROUGH_RATIO:
            listened.add(track_id)
    return listened


def load_examples(label_mode='outcome'):
    """Return (groups, skipped) where each group is one prompt's candidate set."""
    sessions_by_history = {}
    for session in ListeningSession.objects.all().only(
        'prompt_history_id', 'spotify_track_id', 'listen_duration', 'completed'
    ):
        sessions_by_history.setdefault(session.prompt_history_id, []).append((
            str(session.spotify_track_id or '').strip(),
            float(session.listen_duration or 0),
            bool(session.completed),
        ))

    completed_by_history = {
        history_id: {track_id for track_id, _duration, completed in rows if completed}
        for history_id, rows in sessions_by_history.items()
    }

    favorites_by_user = {}
    for favorite in FavoriteTrack.objects.all().only('user_id', 'spotify_track_id'):
        favorites_by_user.setdefault(favorite.user_id, set()).add(
            str(favorite.spotify_track_id or '').strip()
        )

    groups = []
    skipped = {
        'no_candidates': 0,
        'no_selection': 0,
        'selection_absent': 0,
        'opted_out': 0,
        'no_listen_outcome': 0,
    }

    histories = PromptHistory.objects.all().order_by('created_at').iterator()
    for history in histories:
        if not _allows_learning(history):
            skipped['opted_out'] += 1
            continue

        data = _picker_data(history)
        candidates = data.get('candidate_tracks') or []
        candidates = [track for track in candidates if isinstance(track, dict)]
        if len(candidates) < 2:
            skipped['no_candidates'] += 1
            continue

        rows = build_feature_rows(candidates)
        candidate_ids = [str(row['track'].get('id') or '').strip() for row in rows]
        candidates_by_id = {
            str(track.get('id') or '').strip(): track for track in candidates
        }
        completed_ids = completed_by_history.get(history.id, set())
        favorite_ids = favorites_by_user.get(history.user_id, set())

        if label_mode == 'outcome':
            positive_ids = _listened_track_ids(
                history.id, sessions_by_history, candidates_by_id
            ) & set(candidate_ids)
            if not positive_ids or len(positive_ids) == len(candidate_ids):
                # No listen recorded for this prompt, or every candidate was a
                # positive: either way there is no contrast to learn from.
                skipped['no_listen_outcome'] += 1
                continue
        else:
            selected_id = str(data.get('selected_track_id') or '').strip()
            if not selected_id:
                skipped['no_selection'] += 1
                continue
            if selected_id not in candidate_ids:
                # The pick came from outside the recorded candidate set (a
                # fallback path). No contrast, so it is not a row.
                skipped['selection_absent'] += 1
                continue
            positive_ids = {selected_id}

        features = np.array(
            [[row['features'][name] for name in FEATURE_ORDER] for row in rows],
            dtype=float,
        )
        labels = np.array(
            [1 if track_id in positive_ids else 0 for track_id in candidate_ids],
            dtype=int,
        )
        weights = np.array(
            [
                _positive_weight(history, track_id, completed_ids, favorite_ids)
                if track_id in positive_ids
                else 1.0
                for track_id in candidate_ids
            ],
            dtype=float,
        )
        groups.append({
            'history_id': history.id,
            'features': features,
            'labels': labels,
            'weights': weights,
            'positive_positions': [
                index for index, track_id in enumerate(candidate_ids)
                if track_id in positive_ids
            ],
        })

    return groups, skipped


def hit_at_one(groups, weights_vector, bias):
    """Share of prompts where the model's top candidate is the one picked."""
    if not groups:
        return 0.0
    hits = 0
    for group in groups:
        scores = group['features'] @ weights_vector + bias
        if group['labels'][int(np.argmax(scores))] == 1:
            hits += 1
    return hits / len(groups)


def mean_reciprocal_rank(groups, weights_vector, bias):
    if not groups:
        return 0.0
    total = 0.0
    for group in groups:
        scores = group['features'] @ weights_vector + bias
        order = np.argsort(-scores)
        rank = int(np.where(group['labels'][order] == 1)[0][0]) + 1
        total += 1.0 / rank
    return total / len(groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='evaluate but do not write the artifact')
    parser.add_argument('--force', action='store_true', help='write even if the fit loses to the defaults')
    parser.add_argument('--min-prompts', type=int, default=MIN_PROMPTS)
    parser.add_argument(
        '--label',
        choices=('outcome', 'selection'),
        default='outcome',
        help="what counts as a positive; 'selection' is leaky, see module docstring",
    )
    args = parser.parse_args()

    groups, skipped = load_examples(label_mode=args.label)
    print(f"label mode: {args.label}")
    print(f"usable prompts: {len(groups)}")
    print(f"skipped: {skipped}")

    if groups:
        first_slot = sum(1 for group in groups if 0 in group['positive_positions'])
        share = first_slot / len(groups)
        if share > 0.9:
            print(
                f"\nWARNING: the positive is candidate #0 in {first_slot}/{len(groups)} "
                f"prompts ({share:.0%}).\nThe stored candidate list is already ranked, so "
                "this label mostly repeats the\nranking that produced it. Any score below "
                "is measuring leakage, not learning."
            )

    if len(groups) < args.min_prompts:
        print(
            f"\nNot enough data to train ({len(groups)} < {args.min_prompts} prompts).\n"
            "The picker keeps its default weights, which is the correct behaviour."
        )
        if args.label == 'outcome':
            print(
                f"\n{skipped['no_listen_outcome']} prompts had a candidate set but no "
                "usable listen recorded.\nEvery one of those is a training example the app "
                "threw away: the fix is\nlogging a ListeningSession per playback, not "
                "changing the model."
            )
        return 1

    rng = np.random.default_rng(42)
    order = rng.permutation(len(groups))
    split_at = max(int(len(groups) * (1 - TEST_FRACTION)), 1)
    train_groups = [groups[index] for index in order[:split_at]]
    test_groups = [groups[index] for index in order[split_at:]]
    print(f"train prompts: {len(train_groups)}  held-out prompts: {len(test_groups)}")

    features = np.vstack([group['features'] for group in train_groups])
    labels = np.concatenate([group['labels'] for group in train_groups])
    weights = np.concatenate([group['weights'] for group in train_groups])
    print(f"train rows: {features.shape[0]}  positives: {int(labels.sum())}")

    if len(np.unique(labels)) < 2:
        print("Every row carries the same label; nothing to separate.")
        return 1

    model = LogisticRegression(
        max_iter=2000,
        C=1.0,
        class_weight='balanced',
        solver='lbfgs',
    )
    model.fit(features, labels, sample_weight=weights)

    fitted = model.coef_[0].astype(float)
    fitted_bias = float(model.intercept_[0])
    baseline = np.array([DEFAULT_WEIGHTS[name] for name in FEATURE_ORDER], dtype=float)

    evaluation_groups = test_groups or train_groups
    scores = {
        'trained_hit_at_1': hit_at_one(evaluation_groups, fitted, fitted_bias),
        'default_hit_at_1': hit_at_one(evaluation_groups, baseline, DEFAULT_BIAS),
        'trained_mrr': mean_reciprocal_rank(evaluation_groups, fitted, fitted_bias),
        'default_mrr': mean_reciprocal_rank(evaluation_groups, baseline, DEFAULT_BIAS),
    }

    print("\nheld-out comparison")
    print(f"  hit@1   trained {scores['trained_hit_at_1']:.3f}   default {scores['default_hit_at_1']:.3f}")
    print(f"  MRR     trained {scores['trained_mrr']:.3f}   default {scores['default_mrr']:.3f}")
    print("\nlearned weights")
    for name, value in zip(FEATURE_ORDER, fitted):
        print(f"  {name:<20} {value:+.4f}   (default {DEFAULT_WEIGHTS[name]:+.4f})")
    print(f"  {'bias':<20} {fitted_bias:+.4f}")

    improved = scores['trained_hit_at_1'] > scores['default_hit_at_1']
    if not improved and not args.force:
        print(
            "\nThe fitted weights do not beat the defaults on held-out prompts, "
            "so the artifact was NOT written.\nRe-run with --force only if you "
            "know why you want the weaker model."
        )
        return 1

    if args.dry_run:
        print(f"\n--dry-run: not writing {ARTIFACT_PATH}")
        return 0

    payload = {
        'version': datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'),
        'trained_at': datetime.now(timezone.utc).isoformat(),
        'feature_order': list(FEATURE_ORDER),
        'weights': {name: float(value) for name, value in zip(FEATURE_ORDER, fitted)},
        'bias': fitted_bias,
        'metrics': {key: round(float(value), 4) for key, value in scores.items()},
        'train_prompts': len(train_groups),
        'held_out_prompts': len(test_groups),
        'train_rows': int(features.shape[0]),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f"\nwrote {ARTIFACT_PATH}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
