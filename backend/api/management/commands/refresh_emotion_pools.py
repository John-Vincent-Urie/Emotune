"""
Warm the shared per-emotion candidate pools.

Run this on a schedule (cron / systemd timer) and once at deploy time so the
first request after a restart is served from a warm pool instead of paying for
a full chain of live Spotify searches:

    python manage.py refresh_emotion_pools
    python manage.py refresh_emotion_pools --emotions happy,calm --force

Requests warm pools opportunistically too, but only with a playlist's worth of
tracks; this command is what builds pools deep enough to sample from without
handing everyone the same songs.
"""
import time

from django.core.management.base import BaseCommand, CommandError

from api.spotify import pool
from api.spotify_service import spotify_service


class Command(BaseCommand):
    help = 'Refresh the shared per-emotion Spotify candidate pools.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--emotions',
            default='',
            help=(
                'Comma-separated emotions to refresh. '
                f'Defaults to all of: {", ".join(pool.POOL_EMOTIONS)}.'
            ),
        )
        parser.add_argument(
            '--target-size',
            type=int,
            default=None,
            help='Tracks to collect per emotion (defaults to SPOTIFY_TRACK_POOL_TARGET_SIZE).',
        )
        parser.add_argument(
            '--time-budget',
            type=float,
            default=None,
            help='Seconds of Spotify searching per emotion (defaults to SPOTIFY_TRACK_POOL_REFRESH_BUDGET_SECONDS).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Refresh pools that are still fresh instead of skipping them.',
        )
        parser.add_argument(
            '--pause',
            type=float,
            default=2.0,
            help=(
                'Seconds to wait between emotions. Refreshing all of them back '
                'to back sends a few hundred searches in a row and Spotify '
                'starts returning 429, so this paces the run. 0 disables it.'
            ),
        )
        parser.add_argument(
            '--rate-limit-backoff',
            type=float,
            default=30.0,
            help=(
                'Minimum seconds to wait before the single retry given to an '
                'emotion that failed with reason=rate_limited. Spotify\'s own '
                'Retry-After wins when it asks for longer. 0 disables the retry.'
            ),
        )
        parser.add_argument(
            '--max-backoff',
            type=float,
            default=300.0,
            help=(
                'Upper bound on a single Retry-After wait. Spotify can ask for '
                'a very long block after a burst; past this the emotion is left '
                'for the next scheduled run instead of stalling the whole job.'
            ),
        )

    def handle(self, *args, **options):
        if not pool.is_enabled():
            raise CommandError(
                'SPOTIFY_TRACK_POOL_ENABLED is off, so there is nothing to refresh.'
            )

        requested_emotions = [
            pool.normalize_emotion(emotion)
            for emotion in options['emotions'].split(',')
            if emotion.strip()
        ] or list(pool.POOL_EMOTIONS)

        unknown_emotions = [
            emotion for emotion in requested_emotions
            if emotion not in pool.POOL_EMOTIONS
        ]
        if unknown_emotions:
            raise CommandError(
                f'Unknown emotion(s): {", ".join(unknown_emotions)}. '
                f'Known emotions: {", ".join(pool.POOL_EMOTIONS)}.'
            )

        refreshed_count = 0
        skipped_count = 0
        failed_count = 0

        pause_seconds = max(float(options['pause']), 0.0)
        backoff_seconds = max(float(options['rate_limit_backoff']), 0.0)
        max_backoff_seconds = max(float(options['max_backoff']), 0.0)
        is_first_refresh = True

        for emotion in requested_emotions:
            if not options['force']:
                existing_pool = pool.read_pool(emotion)
                if existing_pool and existing_pool['state'] == pool.POOL_STATE_FRESH:
                    skipped_count += 1
                    self.stdout.write(
                        f'{emotion}: still fresh '
                        f'({len(existing_pool["tracks"])} tracks, '
                        f'{existing_pool["age_seconds"] / 60:.0f}m old), skipping'
                    )
                    continue

            # Pace the run; a skipped emotion costs no requests, so the pause
            # only goes between emotions we actually refresh.
            if not is_first_refresh and pause_seconds:
                time.sleep(pause_seconds)
            is_first_refresh = False

            refresh_result = spotify_service.refresh_emotion_pool(
                emotion,
                target_size=options['target_size'],
                time_budget_seconds=options['time_budget'],
            )

            # A 429 means we went too fast, not that the emotion is unusable, so
            # give it one slower retry before recording it as a failure. Spotify
            # states how long it wants us gone in Retry-After, and that block can
            # run to minutes once a burst has tripped it, so prefer its number
            # over our guess.
            if (
                not refresh_result['stored']
                and refresh_result['reason'] == 'rate_limited'
                and backoff_seconds
            ):
                wait_seconds = max(
                    refresh_result.get('retry_after') or 0.0,
                    backoff_seconds,
                )
                if wait_seconds > max_backoff_seconds:
                    self.stderr.write(self.style.WARNING(
                        f'{emotion}: rate limited, Spotify asked for '
                        f'{wait_seconds:.0f}s which is over --max-backoff '
                        f'({max_backoff_seconds:.0f}s); skipping the retry'
                    ))
                else:
                    self.stdout.write(
                        f'{emotion}: rate limited, retrying in {wait_seconds:.0f}s'
                    )
                    time.sleep(wait_seconds)
                    refresh_result = spotify_service.refresh_emotion_pool(
                        emotion,
                        target_size=options['target_size'],
                        time_budget_seconds=options['time_budget'],
                    )

            if refresh_result['stored']:
                refreshed_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'{emotion}: stored {refresh_result["stored"]} tracks '
                    f'from {len(refresh_result["queries_tried"])} queries'
                ))
                continue

            failed_count += 1
            retry_after = refresh_result.get('retry_after')
            retry_note = (
                f', Spotify Retry-After={retry_after:.0f}s'
                if retry_after is not None
                else ''
            )
            self.stderr.write(self.style.WARNING(
                f'{emotion}: no tracks stored '
                f'(reason={refresh_result["reason"]}{retry_note})'
            ))

        summary = (
            f'Refreshed {refreshed_count}, skipped {skipped_count}, failed {failed_count}.'
        )
        self.stdout.write(
            self.style.SUCCESS(summary) if not failed_count else self.style.WARNING(summary)
        )
