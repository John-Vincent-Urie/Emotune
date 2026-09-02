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
            self.stderr.write(self.style.WARNING(
                f'{emotion}: no tracks stored (reason={refresh_result["reason"]})'
            ))

        summary = (
            f'Refreshed {refreshed_count}, skipped {skipped_count}, failed {failed_count}.'
        )
        self.stdout.write(
            self.style.SUCCESS(summary) if not failed_count else self.style.WARNING(summary)
        )
