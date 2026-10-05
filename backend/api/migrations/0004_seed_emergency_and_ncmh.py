"""Seed 911 and the NCMH Crisis Hotline, ahead of Music Cares Studio.

The project owner confirmed both on 2026-10-04 as 24/7 contacts. Music Cares
Studio (0003) is a therapist practice and does not answer at 2am, so these sort
first: emergency services, then the national crisis line, then the therapist.

Only 1553 is seeded for NCMH. The NCMH mobile numbers in the .env.example
comment are not verified -- do not add them here unless the owner verifies them.
"""
import datetime

from django.db import migrations


VERIFIED_ON = datetime.date(2026, 10, 4)

RESOURCES = [
    {
        'name': 'Emergency services (911)',
        'kind': 'emergency',
        'phone': '911',
        'hours': '24/7',
        'description': 'If you or someone else is in immediate danger, call 911 now.',
        'sort_order': 10,
    },
    {
        'name': 'NCMH Crisis Hotline',
        'kind': 'hotline',
        'phone': '1553',
        'hours': '24/7',
        'description': (
            'National Center for Mental Health crisis line. Talk to someone any time, '
            'day or night.'
        ),
        'sort_order': 20,
    },
]


def seed(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    for resource in RESOURCES:
        SupportResource.objects.update_or_create(
            name=resource['name'],
            defaults={
                **{key: value for key, value in resource.items() if key != 'name'},
                'service_mode': 'online',
                'is_verified': True,
                'verified_at': VERIFIED_ON,
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    SupportResource.objects.filter(name__in=[r['name'] for r in RESOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_seed_music_cares_studio'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
