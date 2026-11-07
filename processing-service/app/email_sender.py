"""Sending an email through an SMTP relay (Brevo)

Switched by `EMAIL_ENABLED` (app/config.py): off, nothing is sent and the email is only logged, so
development and the tests never email anyone. `force=True` sends anyway (scripts/send_test_email.py).
"""

import logging
import smtplib
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from . import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attachment:
    """A file attached to an email, e.g. an invoice or receipt PDF."""

    filename: str
    data: bytes
    mime_type: str = 'application/pdf'


class EmailError(Exception):
    """The email wasn't sent. `retryable`: it could work later
    Otherwise it never will: wrong login, an address the relay refuses, or incomplete settings.
    """

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def build_message(
    subject: str, content: str, recipient: str, html: str | None = None, attachments: Sequence[Attachment] = ()
) -> EmailMessage:
    if not config.EMAIL_FROM:
        raise EmailError('EMAIL_FROM is not set', retryable=False)
    message = EmailMessage()
    try:
        message['From'] = formataddr((config.EMAIL_FROM_NAME, config.EMAIL_FROM))
        message['To'] = recipient
        message['Subject'] = subject
    except ValueError as exc:
        raise EmailError(f'Invalid email header: {exc}', retryable=False) from exc
    message.set_content(content)
    if html:
        message.add_alternative(html, subtype='html')
    for attachment in attachments:
        maintype, _, subtype = attachment.mime_type.partition('/')
        try:
            message.add_attachment(attachment.data, maintype=maintype, subtype=subtype or 'octet-stream', filename=attachment.filename)
        except ValueError as exc:
            raise EmailError(f'Invalid attachment {attachment.filename!r}: {exc}', retryable=False) from exc
    return message


def send_email(
    subject: str,
    content: str,
    recipient: str,
    html: str | None = None,
    force: bool = False,
    attachments: Sequence[Attachment] = (),
) -> bool:
    """Returns whether it was sent or not.
    `content`: the plain-text body
    `html`: an optional HTML version.
    `attachments`: files to attach (e.g. the invoice or receipt).
    Raises EmailError when it should have been sent but wasn't.
    """
    if not (config.EMAIL_ENABLED or force):
        logger.info('Email is off (EMAIL_ENABLED): would send "%s" to %s', subject, recipient)
        return False
    message = build_message(subject, content, recipient, html, attachments)
    if not config.SMTP_HOST:
        raise EmailError('SMTP_HOST is not set', retryable=False)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if config.SMTP_USERNAME:
                smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError(f'The SMTP login was refused: {exc.smtp_code}', retryable=False) from exc
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        code = getattr(exc, 'smtp_code', 500)
        raise EmailError(f'The relay refused the email ({code})', retryable=400 <= code < 500) from exc
    except (smtplib.SMTPException, OSError) as exc:
        # can't connect, timeout, dropped connection
        raise EmailError(f'Could not send the email: {exc}', retryable=True) from exc
    logger.info('Sent "%s" to %s', subject, recipient)
    return True