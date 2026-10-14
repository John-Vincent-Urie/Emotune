"""Score api/safety.py crisis detection against the eval sets in api/safety_eval/.

    venv/bin/python manage.py eval_crisis_detection            # both sets
    venv/bin/python manage.py eval_crisis_detection --set dev  # tuning set only

Each text gets one of three outcomes, as the views see it: crisis (no music,
crisis screen), concern (music plus a check-in with resources), or nothing.

- Recall is over crisis items reaching the crisis tier. "Clear" recall is the
  release bar: every unambiguous statement of suicidal or self-harm intent.
- Unflagged counts crisis items that got nothing at all -- the worst outcome.
- Concern items are ambiguous passive phrasing; they pass with either tier.
- False alarms are near-misses sent to the crisis screen; soft alarms are
  near-misses that only got the concern check-in.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from api.safety import SEVERITY_IMMINENT, assess_concern, assess_crisis_severity

EVAL_DIR = Path(__file__).resolve().parents[2] / 'safety_eval'
SETS = ('dev', 'heldout')
TIER_CONCERN = 'concern'


def load_items(name):
    return json.loads((EVAL_DIR / f'{name}.json').read_text(encoding='utf-8'))['items']


def outcome(text):
    """crisis / imminent / concern / None, the way the views would treat `text`."""
    severity = assess_crisis_severity(text)
    if severity:
        return severity
    return TIER_CONCERN if assess_concern(text) else None


def _rate(part, whole):
    return len(part) / max(len(whole), 1)


def score(items):
    results = {i['text']: outcome(i['text']) for i in items}

    def crisis_tier(item):
        return results[item['text']] not in (None, TIER_CONCERN)

    crisis = [i for i in items if i['label'] == 'crisis']
    concern = [i for i in items if i['label'] == 'concern']
    safe = [i for i in items if i['label'] == 'safe']
    clear = [i for i in crisis if i.get('clear')]
    imminent = [i for i in crisis if i.get('severity') == SEVERITY_IMMINENT]

    missed = [i for i in crisis if not crisis_tier(i)]
    return {
        'crisis': len(crisis),
        'concern': len(concern),
        'safe': len(safe),
        'recall': 1 - _rate(missed, crisis),
        'clear_recall': 1 - _rate([i for i in clear if i in missed], clear),
        'clear_total': len(clear),
        'unflagged': [i for i in crisis if results[i['text']] is None],
        'concern_covered': 1 - _rate([i for i in concern if results[i['text']] is None], concern),
        'false_positive_rate': _rate([i for i in safe if crisis_tier(i)], safe),
        'soft_alarm_rate': _rate([i for i in safe if results[i['text']] == TIER_CONCERN], safe),
        'imminent_flagged': sum(1 for i in imminent if results[i['text']] == SEVERITY_IMMINENT),
        'imminent_total': len(imminent),
        'missed': missed,
        'concern_missed': [i for i in concern if results[i['text']] is None],
        'false_alarms': [i for i in safe if crisis_tier(i)],
        'soft_alarms': [i for i in safe if results[i['text']] == TIER_CONCERN],
        'under_severity': [
            i for i in imminent if results[i['text']] not in (None, TIER_CONCERN, SEVERITY_IMMINENT)
        ],
        'results': results,
    }


class Command(BaseCommand):
    help = 'Report crisis-detection recall and false-positive rate on the eval sets.'

    def add_arguments(self, parser):
        parser.add_argument('--set', choices=SETS, action='append', dest='sets')

    def handle(self, *args, **options):
        for name in options['sets'] or SETS:
            result = score(load_items(name))
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n{name}'))
            self.stdout.write(
                f"  recall        {result['recall']:.1%} of {result['crisis']} crisis items reach the crisis tier\n"
                f"  clear recall  {result['clear_recall']:.1%} of {result['clear_total']} clear-intent items\n"
                f"  unflagged     {len(result['unflagged'])} crisis items got nothing at all\n"
                f"  imminent      {result['imminent_flagged']}/{result['imminent_total']} rated high severity\n"
                f"  concern items {result['concern_covered']:.1%} of {result['concern']} got at least a check-in\n"
                f"  false alarms  {result['false_positive_rate']:.1%} of {result['safe']} near-misses sent to crisis\n"
                f"  soft alarms   {result['soft_alarm_rate']:.1%} of near-misses got a check-in"
            )
            for label, rows in (
                ('MISSED', result['missed']),
                ('CONCERN MISSED', result['concern_missed']),
                ('FALSE ALARM', result['false_alarms']),
                ('SOFT ALARM', result['soft_alarms']),
                ('UNDER-RATED', result['under_severity']),
            ):
                for item in rows:
                    flags = ''
                    if item.get('clear'):
                        flags += ' [clear]'
                    if label == 'MISSED':
                        flags += f" [got {result['results'][item['text']] or 'nothing'}]"
                    self.stdout.write(f"    {label}{flags}: {item['text']}")
