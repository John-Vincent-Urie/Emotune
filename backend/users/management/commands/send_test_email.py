"""Prove the mail settings work, without going through the whole reset flow.

`manage.py send_test_email you@gmail.com` reports the effective configuration,
sends one message, and turns the usual SMTP failures into an instruction rather
than a traceback.
"""

import re
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# A Google App Password is exactly 16 lowercase letters, displayed as four
# groups of four. Anything else -- capitals, digits, symbols, a different
# length -- is a normal account password, which Gmail's SMTP always rejects.
APP_PASSWORD_RE = re.compile(r'^[a-z]{16}$')


def app_password_complaint(password):
    """Explain why `password` cannot be a Google App Password, or return None."""
    candidate = re.sub(r'\s+', '', password)
    if APP_PASSWORD_RE.match(candidate):
        return None

    details = [f'{len(candidate)} characters (expected 16)']
    for label, count in (
        ('uppercase letters', sum(c.isupper() for c in candidate)),
        ('digits', sum(c.isdigit() for c in candidate)),
        ('symbols', sum(not c.isalnum() for c in candidate)),
    ):
        if count:
            details.append(f'{count} {label} (expected none)')
    return ', '.join(details)


class Command(BaseCommand):
    help = 'Send a test email through the configured backend.'

    def add_arguments(self, parser):
        parser.add_argument('to', help='Address to send the test message to.')

    def handle(self, *args, **options):
        recipient = options['to']

        self.stdout.write('Effective mail settings:')
        for name in (
            'EMAIL_BACKEND', 'EMAIL_HOST', 'EMAIL_PORT',
            'EMAIL_USE_TLS', 'EMAIL_USE_SSL', 'DEFAULT_FROM_EMAIL',
        ):
            self.stdout.write(f'  {name} = {getattr(settings, name)}')
        self.stdout.write(f'  EMAIL_HOST_USER = {settings.EMAIL_HOST_USER!r}')
        self.stdout.write(
            '  EMAIL_HOST_PASSWORD = '
            + (f'set ({len(settings.EMAIL_HOST_PASSWORD)} chars)'
               if settings.EMAIL_HOST_PASSWORD else 'EMPTY')
        )
        self.stdout.write('')

        if settings.EMAIL_BACKEND == CONSOLE_BACKEND:
            self.stdout.write(self.style.WARNING(
                'Using the console backend, so nothing will reach an inbox: the '
                'message is printed below instead. Set EMAIL_HOST_USER and '
                'EMAIL_HOST_PASSWORD in .env to send for real.'
            ))

        # Checked before connecting: Gmail answers every wrong credential with the
        # same opaque 535, so naming the mismatch here is far more useful.
        if (
            settings.EMAIL_BACKEND != CONSOLE_BACKEND
            and 'gmail' in settings.EMAIL_HOST
            and settings.EMAIL_HOST_PASSWORD
        ):
            complaint = app_password_complaint(settings.EMAIL_HOST_PASSWORD)
            if complaint:
                raise CommandError(
                    'EMAIL_HOST_PASSWORD is not a Google App Password.\n'
                    f'  Found: {complaint}.\n'
                    '  An App Password is 16 lowercase letters, shown once as four\n'
                    '  groups of four at myaccount.google.com/apppasswords\n'
                    '  (the page needs 2-Step Verification switched on first).'
                )

        try:
            sent = send_mail(
                subject='EmoTune test email',
                message=(
                    'If you are reading this in your inbox, the password reset '
                    'code will reach you too.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except smtplib.SMTPAuthenticationError as exc:
            raise CommandError(
                'Gmail rejected the credentials.\n'
                '  - EMAIL_HOST_PASSWORD must be a 16-character App Password, '
                'not your Google account password.\n'
                '  - App passwords need 2-Step Verification turned on first:\n'
                '    Google Account > Security > 2-Step Verification > App passwords\n'
                '  - EMAIL_HOST_USER must be the full address, e.g. you@gmail.com\n'
                f'  SMTP said: {exc}'
            ) from exc
        except smtplib.SMTPException as exc:
            raise CommandError(f'SMTP refused the message: {exc}') from exc
        except OSError as exc:
            # Wrong port, no route, TLS mismatch -- all surface as OSError.
            raise CommandError(
                f'Could not reach {settings.EMAIL_HOST}:{settings.EMAIL_PORT} -- {exc}\n'
                '  Gmail wants port 587 with EMAIL_USE_TLS=true, '
                'or port 465 with EMAIL_USE_SSL=true.'
            ) from exc

        if sent:
            self.stdout.write(self.style.SUCCESS(f'Sent 1 message to {recipient}.'))
        else:
            raise CommandError('The backend reported that nothing was sent.')
