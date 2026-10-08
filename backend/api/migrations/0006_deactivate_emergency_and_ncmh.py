"""Deactivate 911 and the NCMH Crisis Hotline, pending replacement contacts.

Owner decision, 2026-10-08: these two rows (seeded in 0004) are coming out of
the shown contacts while replacement numbers are sourced and verified. This
sets `is_active=False` rather than deleting the rows -- `SupportResource.visible()`
already excludes inactive rows, and `is_active` exists on the model precisely
for this "temporarily not shown" case, so the verified_at/is_verified history
is not lost and the rows are easy to reactivate if the decision changes.

Music Cares Studio (0003) is untouched and is, for now, the only entry left in
`/api/support-resources/`. Its own description still says "call emergency
services first" -- see the matching change to the Flutter bundled fallback in
flutter_app/lib/services/support_contacts.dart, which no longer lists an
emergency/crisis-line entry for that sentence to point at.
"""
from django.db import migrations

NAMES = ['Emergency services (911)', 'NCMH Crisis Hotline']


def deactivate(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    SupportResource.objects.filter(name__in=NAMES).update(is_active=False)


def reactivate(apps, schema_editor):
    SupportResource = apps.get_model('api', 'SupportResource')
    SupportResource.objects.filter(name__in=NAMES).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_seed_emergency_and_ncmh'),
    ]

    operations = [
        migrations.RunPython(deactivate, reactivate),
    ]
