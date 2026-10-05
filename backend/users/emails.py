"""Outbound mail for the credential flows.

Kept apart from the views so a failure to send is easy to spot in a traceback
and the message copy is in one place rather than inline in a request handler.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

from .models import PasswordResetCode


def _lifetime_minutes():
    return int(PasswordResetCode.LIFETIME.total_seconds() // 60)


def send_password_reset_code(user, code):
    """Email a one-time reset code. Raises if the mail cannot be handed off."""
    minutes = _lifetime_minutes()
    greeting = user.username or 'there'

    subject = 'Your EmoTune password reset code'
    text_body = (
        f'Hi {greeting},\n\n'
        f'Your EmoTune password reset code is:\n\n'
        f'    {code}\n\n'
        f'Enter it in the app within {minutes} minutes to choose a new '
        f'password. The code can only be used once.\n\n'
        f'If you did not ask to reset your password you can ignore this '
        f'email -- your current password still works.\n\n'
        f'-- EmoTune'
    )

    # Spaced out and oversized: the whole job of this mail is to make six
    # digits easy to read off a phone notification and type into the app.
    html_body = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
                max-width:480px;margin:0 auto;padding:32px 24px;
                background:#050608;color:#F3F6F3;border-radius:16px">
      <p style="font-size:15px;color:#93A199;margin:0 0 24px">Hi {escape(greeting)},</p>
      <p style="font-size:15px;margin:0 0 20px">
        Here is your EmoTune password reset code:
      </p>
      <p style="font-size:34px;font-weight:700;letter-spacing:10px;
                margin:0 0 24px;color:#CFF24A">{escape(code)}</p>
      <p style="font-size:14px;color:#93A199;margin:0 0 8px">
        Enter it in the app within {minutes} minutes to choose a new password.
        It only works once.
      </p>
      <p style="font-size:13px;color:#5C6A61;margin:24px 0 0">
        Did not ask for this? Ignore this email -- your current password still works.
      </p>
    </div>
    """

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, 'text/html')
    message.send(fail_silently=False)
