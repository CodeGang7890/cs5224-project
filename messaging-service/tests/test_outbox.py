"""The outbox (app/outbox.py): sending saved WhatsApp replies, in order, with retries; and the
consumer's sweeper. On SQLite (no row locks: the SKIP LOCKED part is PostgreSQL's), sending mocked."""

import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

from app import config, outbox
from app.chat_flow import dates
from app.consumer import Consumer
from app.models import OutboundMessage
from app.whatsapp_sender import SendError

from .chat_helpers import DatabaseTestCase


class OutboxTestCase(DatabaseTestCase):
    """A business with two real chats, and helpers to queue replies and send them."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.chat = self.make.session(self.cafe, phone_number='+6591234567', is_sandbox=False)
        self.other_chat = self.make.session(self.cafe, phone_number='+6598765432', is_sandbox=False)
        self.now = dates.now()
        sender = patch('app.whatsapp_sender.send_text', side_effect=lambda business_id, to, text: f'wamid.{text}')
        self.send_text = sender.start()
        self.addCleanup(sender.stop)

    def queue(self, text, chat=None, **fields):
        chat = chat or self.chat
        with self.sessions.begin() as db:
            item = OutboundMessage(
                business_id=self.cafe.id, chat_session_id=chat.id, inbound_message_id=None, text=text,
                status=fields.pop('status', outbox.PENDING), attempts=fields.pop('attempts', 0),
                next_attempt_time=fields.pop('next_attempt_time', self.now), last_error='', meta_message_id='',
                created_time=self.now, sent_time=fields.pop('sent_time', None),
            )
            db.add(item)
        return item

    def send(self, at=None, **kwargs):
        with self.assertLogs('app.outbox', level='INFO'):
            return outbox.send_due(self.sessions, now=at or self.now, **kwargs)

    def statuses(self):
        return [(item.text, item.status, item.attempts) for item in self.all(OutboundMessage)]


class OutboxTests(OutboxTestCase):
    def test_sends_whats_due_in_order(self):
        self.queue('welcome')
        self.queue('reply')
        done = self.send()
        self.assertEqual((done.sent, done.retrying, done.failed), (2, 0, 0))
        self.assertEqual(
            [call.args for call in self.send_text.call_args_list],
            [(self.cafe.id, '+6591234567', 'welcome'), (self.cafe.id, '+6591234567', 'reply')],
        )
        first, second = self.all(OutboundMessage)
        self.assertEqual((first.status, first.meta_message_id, first.attempts, first.last_error), ('sent', 'wamid.welcome', 1, ''))
        self.assertIsNotNone(first.sent_time)

    def test_a_failure_is_retried_with_a_growing_delay_then_given_up(self):
        self.send_text.side_effect = SendError('Not sent (503): Meta is down')
        self.queue('reply')
        at, delays = self.now, []
        for attempt in range(1, config.OUTBOX_ATTEMPTS_MAX + 1):
            with patch('app.outbox.dates.now', return_value=at):  # the retry time is counted from now
                done = self.send(at)
            item, = self.all(OutboundMessage)
            self.assertEqual(item.attempts, attempt)
            self.assertIn('Meta is down', item.last_error)
            if attempt < config.OUTBOX_ATTEMPTS_MAX:
                self.assertEqual((item.status, done.retrying), ('pending', 1))
                delays.append(item.next_attempt_time - at)
                self.assertEqual(outbox.send_due(self.sessions, now=item.next_attempt_time - timedelta(seconds=1)).retrying, 0)
                at = item.next_attempt_time  # not before then
        self.assertEqual((item.status, done.failed), ('failed', 1))
        self.assertEqual(delays, [timedelta(seconds=s) for s in (10, 30, 120, 600)])
        self.assertEqual(outbox.send_due(self.sessions, now=at + timedelta(days=1)).failed, 0)  # never again

    def test_a_refusal_fails_at_once_but_rate_limits_and_outages_are_retried(self):
        for status_code, expected in (
            (404, 'failed'), (400, 'failed'), (403, 'pending'), (429, 'pending'), (502, 'pending'), (503, 'pending'), (None, 'pending'),
        ):
            with self.subTest(status_code=status_code):
                self.send_text.side_effect = SendError(f'Not sent ({status_code})', status_code)
                item = self.queue(f'reply {status_code}', chat=self.make.session(self.cafe, phone_number=f'+65900{status_code}', is_sandbox=False))
                with self.assertLogs('app.outbox', level='WARNING'):
                    outbox.send_due(self.sessions, now=self.now, chat_session_id=item.chat_session_id)
                saved = self.get(OutboundMessage, item.id)
                self.assertEqual((saved.status, saved.attempts), (expected, 1))

    def test_an_earlier_pending_message_holds_back_the_rest_of_its_chat_only(self):
        self.queue('first', next_attempt_time=self.now + timedelta(minutes=1))  # waiting for a retry
        self.queue('second')
        self.queue('elsewhere', chat=self.other_chat)
        done = self.send()
        self.assertEqual(done.sent, 1)
        self.assertEqual(
            self.statuses(), [('first', 'pending', 0), ('second', 'pending', 0), ('elsewhere', 'sent', 1)]
        )
        self.send(self.now + timedelta(minutes=1))  # first is due: then second goes too
        self.assertEqual([status for _, status, _ in self.statuses()], ['sent', 'sent', 'sent'])

    def test_a_failed_message_no_longer_holds_back_its_chat(self):
        self.queue('given up', status=outbox.FAILED, attempts=config.OUTBOX_ATTEMPTS_MAX)
        self.queue('next')
        self.assertEqual(self.send().sent, 1)
        self.assertEqual(self.statuses()[1], ('next', 'sent', 1))
        self.assertEqual(self.send_text.call_count, 1)

    def test_a_failure_in_the_middle_stops_its_chat_until_the_retry(self):
        self.send_text.side_effect = [SendError('Not sent (502): refused'), 'wamid.other']
        self.queue('first')
        self.queue('second')
        self.queue('elsewhere', chat=self.other_chat)
        with self.assertLogs('app.outbox', level='INFO'):
            done = outbox.send_due(self.sessions, now=self.now)
        self.assertEqual((done.sent, done.retrying), (1, 1))
        self.assertEqual(self.statuses(), [('first', 'pending', 1), ('second', 'pending', 0), ('elsewhere', 'sent', 1)])

    def test_an_unexpected_error_counts_as_a_failed_attempt(self):
        self.send_text.side_effect = RuntimeError('bug')
        self.queue('reply')
        with self.assertLogs('app.outbox', level='ERROR') as logs:
            done = outbox.send_due(self.sessions, now=self.now)
        self.assertEqual(done.retrying, 1)
        self.assertIn('failed unexpectedly', logs.output[0])
        self.assertEqual(self.statuses(), [('reply', 'pending', 1)])

    def test_only_one_chat(self):
        self.queue('mine')
        self.queue('elsewhere', chat=self.other_chat)
        self.send(chat_session_id=self.chat.id)
        self.assertEqual(self.statuses(), [('mine', 'sent', 1), ('elsewhere', 'pending', 0)])

    def test_nothing_due(self):
        self.queue('sent', status=outbox.SENT, sent_time=self.now)
        self.queue('later', next_attempt_time=self.now + timedelta(seconds=5))
        done = outbox.send_due(self.sessions, now=self.now)
        self.assertEqual((done.sent, done.retrying, done.failed), (0, 0, 0))
        self.send_text.assert_not_called()

    def test_retry_delay(self):
        self.assertEqual([outbox.retry_delay(n).total_seconds() for n in (1, 2, 3, 4, 5, 9)], [10, 30, 120, 600, 600, 600])


class SweeperTests(OutboxTestCase):
    """The consumer's sweeper sends what's due in the background, and stops with the consumer."""

    def test_sends_due_replies_in_the_background(self):
        self.queue('left by a worker that died')
        pull = Consumer(subscriber=MagicMock(), sessions=self.sessions, sweep_seconds=0.01)
        with self.assertLogs('app', level='INFO'):
            pull.start()
            for _ in range(200):
                if self.all(OutboundMessage)[0].status == 'sent':
                    break
                time.sleep(0.01)
            pull.stop()
        self.assertEqual(self.statuses(), [('left by a worker that died', 'sent', 1)])
        self.assertIsNone(pull._sweeper)

    def test_restarted_with_a_new_stop_signal(self):
        pull = Consumer(subscriber=MagicMock(), sessions=self.sessions, sweep_seconds=60)
        with self.assertLogs('app.consumer', level='INFO'):
            pull.start()
            first = pull._stopping
            pull.stop()
            pull.start()
            self.assertIsNot(pull._stopping, first)
            self.assertTrue(first.is_set())  # the old sweeper stays stopped
            pull.stop()

    def test_off_with_zero(self):
        pull = Consumer(subscriber=MagicMock(), sessions=self.sessions, sweep_seconds=0)
        with self.assertLogs('app.consumer', level='INFO'):
            pull.start()
            pull.stop()
        self.assertIsNone(pull._sweeper)
