"""Seed the support contact the project owner verified on 2026-10-04.

A data migration rather than an admin entry so a fresh database (a new dev box,
the test DB, a redeploy) still shows it on the crisis screen.

Music Cares Studio is a therapist practice, not a 24/7 crisis line, so the
description says so and no hours are claimed. It has one number per mobile
network, and SupportResource holds one phone each, so it is two rows: people in
the Philippines usually call the number on their own network.

Do not add other numbers here unless the project owner has verified them.
"""
import datetime

from django.db import migrations


VERIFIED_ON = datetime.date(2026, 10, 4)

DESCRIPTION = (
    'Therapist service. Not a 24/7 crisis line -- if you are in immediate danger, '
    'call emergency services first.'
)

RESOURCES = [
    {'name': 'Music Cares Studio (Globe)', 'phone': '09173255789', 'sort_order': 50},
    {'name': 'Music Cares Studio (Smart)', 'phone': '09189296012', 'sort_order': 51},
]


def seed(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    for resource in RESOURCES:
        SupportResource.objects.update_or_create(
            name=resource['name'],
            defaults={
                'kind': 'counselor',
                'description': DESCRIPTION,
                'phone': resource['phone'],
                'service_mode': 'online',
                'is_verified': True,
                'verified_at': VERIFIED_ON,
                'is_active': True,
                'sort_order': resource['sort_order'],
            },
        )


def unseed(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    SupportResource.objects.filter(name__in=[r['name'] for r in RESOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_support_resources_and_events'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
