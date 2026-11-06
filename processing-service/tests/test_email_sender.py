import smtplib
import unittest
from unittest import mock

from app import config, email_sender
from app.email_sender import Attachment, EmailError, send_email


SETTINGS = dict(EMAIL_ENABLED=True, EMAIL_FROM='noreply@example.com', EMAIL_FROM_NAME='Ansera', SMTP_HOST='smtp.example.com',
                SMTP_PORT=587, SMTP_USERNAME='login', SMTP_PASSWORD='key')


class SendEmailTests(unittest.TestCase):
    def setUp(self):
        self.set_config()

    def set_config(self, **overrides):
        for name, value in {**SETTINGS, **overrides}.items():
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def send(self, **kwargs):
        with mock.patch.object(email_sender.smtplib, 'SMTP') as smtp_cls:
            result = send_email('Your invoice', 'Thanks for shopping with XXX, this is your invoice.', 'customer@mail.com', **kwargs)
        return result, smtp_cls, smtp_cls.return_value.__enter__.return_value

    def test_sends_through_starttls_with_the_login(self):
        sent, smtp_cls, smtp = self.send()
        self.assertTrue(sent)
        self.assertEqual(smtp_cls.call_args.args, ('smtp.example.com', 587))
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with('login', 'key')
        message = smtp.send_message.call_args.args[0]
        self.assertEqual((message['To'], message['Subject']), ('customer@mail.com', 'Your invoice'))
        self.assertEqual(message['From'], 'Ansera <noreply@example.com>')
        self.assertEqual(message.get_content().strip(), 'Thanks for shopping with XXX, this is your invoice.')

    def test_attaches_files(self):
        _, _, smtp = self.send(attachments=[Attachment('RCT-O-000001.pdf', b'%PDF-fake')])
        message = smtp.send_message.call_args.args[0]
        [attachment] = list(message.iter_attachments())
        self.assertEqual((attachment.get_filename(), attachment.get_content_type()), ('RCT-O-000001.pdf', 'application/pdf'))
        self.assertEqual(attachment.get_content(), b'%PDF-fake')
        self.assertEqual(message.get_body().get_content().strip(), 'Thanks for shopping with XXX, this is your invoice.')

    def test_a_filename_with_a_line_break_is_refused(self):
        with mock.patch.object(email_sender.smtplib, 'SMTP') as smtp_cls, self.assertRaises(EmailError) as caught:
            send_email('Hi', 'Body', 'customer@example.com', attachments=[Attachment('a.pdf\r\nBcc: x@y.z', b'x')])
        self.assertFalse(caught.exception.retryable)
        smtp_cls.assert_not_called()

    def test_html_is_an_alternative_to_the_text(self):
        _, _, smtp = self.send(html='<p>Thanks for shopping with XXX, this is your invoice.</p>')
        message = smtp.send_message.call_args.args[0]
        self.assertEqual([part.get_content_type() for part in message.iter_parts()], ['text/plain', 'text/html'])

    def test_off_means_nothing_is_sent(self):
        self.set_config(EMAIL_ENABLED=False)
        with mock.patch.object(email_sender.smtplib, 'SMTP') as smtp_cls:
            self.assertFalse(send_email('Hi', 'Body', 'customer@example.com'))
        smtp_cls.assert_not_called()

    def test_force_sends_even_when_off(self):
        self.set_config(EMAIL_ENABLED=False)
        sent, *_ = self.send(force=True)
        self.assertTrue(sent)

    def test_which_failures_are_worth_retrying(self):
        cases = [
            (smtplib.SMTPAuthenticationError(535, b'bad login'), False),
            (smtplib.SMTPRecipientsRefused({'baduser@mail.com': (550, b'no such user')}), False),
            (smtplib.SMTPDataError(451, b'try again later'), True),
            (smtplib.SMTPServerDisconnected('gone'), True),
            (TimeoutError('timed out'), True),
            (ConnectionRefusedError('refused'), True),
        ]
        for error, retryable in cases:
            with self.subTest(error=type(error).__name__), mock.patch.object(email_sender.smtplib, 'SMTP', side_effect=error), \
                    self.assertRaises(EmailError) as caught:
                send_email('Hi', 'Body', 'customer@example.com')
            self.assertEqual(caught.exception.retryable, retryable)

    def test_a_line_break_in_the_subject_cannot_inject_a_header(self):
        with mock.patch.object(email_sender.smtplib, 'SMTP') as smtp_cls, self.assertRaises(EmailError) as caught:
            send_email('Hi\r\nBcc: someone@else.com', 'Body', 'customer@example.com')
        self.assertFalse(caught.exception.retryable)
        smtp_cls.assert_not_called()

    def test_incomplete_settings_are_an_error_not_a_silent_skip(self):
        self.set_config(EMAIL_FROM='')
        with self.assertRaises(EmailError) as caught:
            send_email('Hi', 'Body', 'customer@example.com')
        self.assertFalse(caught.exception.retryable)