#!/usr/bin/env python3
"""Build the known-word list the input check uses to spot gibberish.

A word is "known" when it appears at least MIN_COUNT times across the project's
own English and Taglish text corpora. The list is written to
backend/api/data/known_words.txt, one word per line, sorted, so it can be
reviewed and diffed like any other source file. Re-run this after adding a
corpus; the output is deterministic.

    python3 ml_model/build_known_words.py
"""
from collections import Counter
import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / 'dataset'
OUTPUT_PATH = ROOT / 'backend' / 'api' / 'data' / 'known_words.txt'

# (file, text column). English: GoEmotions and the 150k text-emotion set.
# Tagalog/Taglish: the FiReCS product reviews and EmoTune's own datasets.
CORPORA = (
    ('goemotions.cleaned.csv', 'text'),
    ('text_emotion_classification.cleaned.csv', 'text'),
    ('firecs_taglish_reviews.csv', 'text'),
    ('emotune_combined.csv', 'text'),
    ('emotune_dataset_1200.csv', 'text'),
    ('emotune_custom_dataset.csv', 'text'),
    ('emotune_anger_1000.csv', 'text'),
    ('emotune_depression_1000.csv', 'text'),
    ('stress.csv', 'text'),
)

# Seen this often, a token is a real word (or real slang), not a typo or a mash.
MIN_COUNT = 3
MAX_WORD_LENGTH = 20

# Must match api/input_validation.py's tokenizer.
WORD_PATTERN = re.compile(r"[a-zñ]+(?:'[a-z]+)?")


def iter_texts(path, column):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            text = row.get(column)
            if text:
                yield text


def main():
    csv.field_size_limit(sys.maxsize)
    counts = Counter()
    for name, column in CORPORA:
        path = DATASET_DIR / name
        if not path.exists():
            print(f'skip (missing): {name}')
            continue
        rows = 0
        for text in iter_texts(path, column):
            counts.update(WORD_PATTERN.findall(text.lower()))
            rows += 1
        print(f'{name}: {rows} rows')

    words = sorted(
        word for word, count in counts.items()
        if count >= MIN_COUNT and len(word) <= MAX_WORD_LENGTH
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text('\n'.join(words) + '\n', encoding='utf-8')
    print(f'{len(words)} known words -> {OUTPUT_PATH.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
