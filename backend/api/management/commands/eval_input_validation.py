"""Score the analyze input checks on a labelled CSV, per category.

    python manage.py eval_input_validation
    python manage.py eval_input_validation --split test
    python manage.py eval_input_validation --sweep     # tune thresholds on dev rows
    python manage.py eval_input_validation --cache predictions.json

--cache keeps the classifier's output per text in a JSON file (read if it
exists, written back after the run), so repeat runs and threshold sweeps do
not reload BERT. The model only loads for texts missing from the cache.

Each row runs exactly what /api/analyze/ runs before choosing songs: the crisis
check, then `decide_after_crisis` with the real classifier. A row "passes" when
the input_status matches; for emotion-word rows the emotion must match too.
An expected status may list alternatives ("unclear|off_topic") where either
answer asks the user again. Rows the crisis check catches are reported separately: crisis always wins, by
design, so they are not counted as misses.
"""
from collections import defaultdict
import csv
import json
from itertools import product
from pathlib import Path
from unittest.mock import patch

from django.core.management.base import BaseCommand

from api import input_validation
from api.input_validation import decide_after_crisis
from api.safety import assess_crisis_severity
from ml.emotion_classifier import get_classifier

DEFAULT_CSV = Path(__file__).resolve().parents[4] / 'dataset' / 'input_validation_eval.csv'
CATEGORY_ORDER = (
    'gibberish', 'non_english', 'emotion_word', 'off_topic', 'vague',
    'neutral_self', 'feeling', 'tricky_english',
)


class Command(BaseCommand):
    help = 'Per-category accuracy of the analyze input checks on a labelled CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--csv', default=str(DEFAULT_CSV))
        parser.add_argument('--split', choices=('dev', 'test', 'all'), default='all')
        parser.add_argument('--cache', help='JSON file of classifier outputs keyed by text.')
        parser.add_argument(
            '--sweep', action='store_true',
            help='Grid-search the model thresholds on dev rows and print the best.',
        )

    def handle(self, *args, **options):
        with open(options['csv'], encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        cache_path = Path(options['cache']) if options['cache'] else None
        cache = (
            json.loads(cache_path.read_text(encoding='utf-8'))
            if cache_path and cache_path.exists()
            else {}
        )
        cached_count = len(cache)

        def predict(text):
            if text not in cache:
                cache[text] = get_classifier().predict(text)
            return cache[text]

        if options['sweep']:
            self._sweep([row for row in rows if row['split'] == 'dev'], predict)
        else:
            selected = rows if options['split'] == 'all' else [
                row for row in rows if row['split'] == options['split']
            ]
            self._report(selected, predict, options['split'])
        if cache_path and len(cache) != cached_count:
            cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding='utf-8')

    def _run(self, row, predict):
        text = row['text']
        if assess_crisis_severity(text):
            return 'crisis', None, 'crisis'
        decision = decide_after_crisis(text, predict)
        return decision.status, decision.emotion, decision.reason

    def _passes(self, row, status, emotion):
        # "unclear|off_topic": either answer is right (both ask the user again).
        if status not in row['expected_status'].split('|'):
            return False
        if row['category'] == 'emotion_word':
            return emotion == row['expected_emotion']
        return True

    def _score(self, rows, predict):
        per_category = defaultdict(lambda: [0, 0])
        misses, crisis_rows = [], []
        for row in rows:
            status, emotion, reason = self._run(row, predict)
            if status == 'crisis':
                crisis_rows.append(row)
                continue
            ok = self._passes(row, status, emotion)
            per_category[row['category']][0] += int(ok)
            per_category[row['category']][1] += 1
            if not ok:
                misses.append((row, status, emotion, reason))
        return per_category, misses, crisis_rows

    def _report(self, rows, predict, split):
        per_category, misses, crisis_rows = self._score(rows, predict)
        self.stdout.write(f'Input check accuracy ({split} rows, {len(rows)} total)\n')
        self.stdout.write(f"{'category':<16}{'correct':>9}{'total':>7}{'accuracy':>10}")
        correct_all = total_all = 0
        for category in CATEGORY_ORDER:
            if category not in per_category:
                continue
            correct, total = per_category[category]
            correct_all += correct
            total_all += total
            self.stdout.write(f'{category:<16}{correct:>9}{total:>7}{correct / total:>10.1%}')
        if total_all:
            self.stdout.write(
                f"{'overall':<16}{correct_all:>9}{total_all:>7}{correct_all / total_all:>10.1%}"
            )

        feeling_rows = [row for row in rows if row['category'] in ('feeling', 'tricky_english')]
        agree = graded = 0
        for row in feeling_rows:
            status, emotion, _reason = self._run(row, predict)
            if status == 'ok' and row['expected_emotion']:
                graded += 1
                agree += int(emotion == row['expected_emotion'])
        if graded:
            self.stdout.write(
                f'\nEmotion agreement on accepted feeling sentences: {agree}/{graded} '
                f'({agree / graded:.1%}) -- informative only; the label is our guess.'
            )
        if crisis_rows:
            self.stdout.write(f'\nCaught by the crisis check first (not scored): {len(crisis_rows)}')
            for row in crisis_rows:
                self.stdout.write(f'  [{row["category"]}] {row["text"]}')
        if misses:
            self.stdout.write('\nMisses (expected -> got, rule):')
            for row, status, emotion, reason in misses:
                got = f'{status}/{emotion}' if emotion else status
                want = row['expected_status'] + (
                    f"/{row['expected_emotion']}" if row['category'] == 'emotion_word' else ''
                )
                self.stdout.write(f'  [{row["category"]}] {row["text"]!r}: {want} -> {got} ({reason})')

    def _sweep(self, rows, predict):
        grid = product(
            (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80),
            (0.0, 0.05, 0.10, 0.15, 0.20, 0.30),
            (0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.01),
        )
        results = []
        for confidence, margin, without_affect in grid:
            with patch.multiple(
                input_validation,
                MIN_MODEL_CONFIDENCE=confidence,
                MIN_MODEL_MARGIN=margin,
                MIN_MODEL_CONFIDENCE_WITHOUT_AFFECT=without_affect,
            ):
                per_category, _misses, _crisis = self._score(rows, predict)
            # Balanced accuracy: every category counts equally, so a big
            # category cannot hide a broken small one.
            accuracies = [correct / total for correct, total in per_category.values() if total]
            balanced = sum(accuracies) / len(accuracies)
            results.append((balanced, confidence, margin, without_affect, dict(per_category)))
        results.sort(key=lambda item: -item[0])
        self.stdout.write('Top threshold settings on dev rows (balanced accuracy):')
        for balanced, confidence, margin, without_affect, per_category in results[:10]:
            detail = ', '.join(
                f'{category} {correct}/{total}'
                for category, (correct, total) in sorted(per_category.items())
            )
            self.stdout.write(
                f'  {balanced:.3f}  conf>={confidence:.2f} margin>={margin:.2f} '
                f'no-affect conf>={without_affect:.2f} | {detail}'
            )
