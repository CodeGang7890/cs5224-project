from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from product_app.models import FAQ, FAQ_QUESTION_MAX_LENGTH

from ..models import ChatSession, QuestionStatus, UnansweredQuestion
from ..questions import (
    ANSWER_MAX_LENGTH,
    answer_message,
    answer_question,
)
from ..validators import CHAT_MESSAGE_MAX_LENGTH, validate_chat_messages


class QuestionTestData:
    """Two businesses, each with a user and chats; plus a user with no business."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.florist_user = BusinessUser.objects.create_user(username='florist', password='123', business=cls.florist)
        cls.no_business_user = BusinessUser.objects.create_user(username='nobiz', password='123')
        cls.alice = ChatSession.objects.create(business=cls.cafe, phone_number='+6591234567', display_name='Alice')
        cls.sandbox = ChatSession.objects.create(business=cls.cafe, is_sandbox=True, display_name='Test chat 1')
        cls.rose_chat = ChatSession.objects.create(business=cls.florist, phone_number='+6598765432')

    def make_question(self, session, question='Do you have oat milk?', **fields):
        return UnansweredQuestion.objects.create(
            business_id=session.business_id, chat_session=session, question=question, **fields
        )


class UnansweredQuestionModelTests(QuestionTestData, TestCase):
    def test_defaults(self):
        item = self.make_question(self.alice)
        item.full_clean()
        self.assertEqual(item.status, QuestionStatus.OPEN)
        self.assertIsNone(item.answered_time)
        self.assertIsNone(item.faq)
        self.assertLess(timezone.now() - item.created_time, timedelta(seconds=5))
        self.assertEqual(str(item), 'Do you have oat milk?')

    def test_question_limits(self):
        with self.assertRaises(ValidationError):
            UnansweredQuestion(business=self.cafe, chat_session=self.alice, question='').full_clean()
        with self.assertRaises(ValidationError):
            UnansweredQuestion(
                business=self.cafe, chat_session=self.alice, question='x' * (FAQ_QUESTION_MAX_LENGTH + 1)
            ).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_question(self.alice, question='')

    def test_status_must_be_valid(self):
        with self.assertRaises(ValidationError):
            UnansweredQuestion(business=self.cafe, chat_session=self.alice, question='Q?', status='closed').full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_question(self.alice, status='closed')

    def test_answered_time_is_set_exactly_when_answered(self):
        now = timezone.now()
        self.make_question(self.alice, status=QuestionStatus.ANSWERED, answered_time=now)  # fine
        for fields in (
            {'status': QuestionStatus.ANSWERED},  # answered without a time
            {'status': QuestionStatus.OPEN, 'answered_time': now},
            {'status': QuestionStatus.DISMISSED, 'answered_time': now},
        ):
            with self.subTest(**fields):
                with self.assertRaises(ValidationError):
                    UnansweredQuestion(business=self.cafe, chat_session=self.alice, question='Q?', **fields).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.make_question(self.alice, **fields)

    def test_chat_and_faq_must_belong_to_the_business(self):
        item = UnansweredQuestion(business=self.cafe, chat_session=self.rose_chat, question='Q?')
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn('chat_session', ctx.exception.message_dict)
        florist_faq = FAQ.objects.create(business=self.florist, question='Delivery?', answer='No.')
        item = UnansweredQuestion(business=self.cafe, chat_session=self.alice, question='Q?', faq=florist_faq)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn('faq', ctx.exception.message_dict)

    def test_deleted_with_its_chat_or_business(self):
        self.make_question(self.sandbox)
        self.sandbox.delete()
        self.assertFalse(UnansweredQuestion.objects.exists())
        self.make_question(self.alice)
        self.cafe.delete()
        self.assertFalse(UnansweredQuestion.objects.exists())

    def test_faq_deleted_keeps_the_question(self):
        faq = FAQ.objects.create(business=self.cafe, question='Oat milk?', answer='Yes.')
        item = self.make_question(self.alice, status=QuestionStatus.ANSWERED, answered_time=timezone.now(), faq=faq)
        faq.delete()
        item.refresh_from_db()
        self.assertEqual((item.status, item.faq), (QuestionStatus.ANSWERED, None))

    def test_newest_first(self):
        old = self.make_question(self.alice, question='Old?', created_time=timezone.now() - timedelta(days=1))
        new = self.make_question(self.alice, question='New?')
        self.assertEqual(list(UnansweredQuestion.objects.all()), [new, old])


NO_QUESTION_CHECK = {'kind': 'none', 'question': None}


class QuestionAPITestCase(QuestionTestData, APITestCase):
    list_url = reverse('chat_app:question-list')

    @staticmethod
    def answer_url(item):
        return reverse('chat_app:question-answer', args=[item.pk])

    @staticmethod
    def dismiss_url(item):
        return reverse('chat_app:question-dismiss', args=[item.pk])


class UnansweredQuestionListAPITests(QuestionAPITestCase):
    def setUp(self):
        now = timezone.now()
        self.open_q = self.make_question(self.alice, 'Do you have oat milk?', created_time=now - timedelta(hours=3))
        self.faq = FAQ.objects.create(business=self.cafe, question='Are you halal?', answer='No pork or lard.')
        self.answered_q = self.make_question(
            self.alice, 'Are you halal?', status='answered', answered_time=now, faq=self.faq,
            created_time=now - timedelta(hours=2),
        )
        self.dismissed_q = self.make_question(self.alice, 'Hiring?', status='dismissed', created_time=now - timedelta(hours=1))
        self.sandbox_q = self.make_question(self.sandbox, 'Parking?', created_time=now)
        self.florist_q = self.make_question(self.rose_chat, 'Sunflowers?')

    def ids(self, params=None):
        response = self.client.get(self.list_url, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return [item['id'] for item in response.json()['results']]

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_lists_only_own_questions_newest_first(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids(), [self.sandbox_q.pk, self.dismissed_q.pk, self.answered_q.pk, self.open_q.pk])
        self.client.force_authenticate(self.florist_user)
        self.assertEqual(self.ids(), [self.florist_q.pk])

    def test_fields(self):
        self.client.force_authenticate(self.cafe_user)
        results = {item['id']: item for item in self.client.get(self.list_url).json()['results']}
        answered = results[self.answered_q.pk]
        self.assertEqual(
            {k: answered[k] for k in ('business', 'chat_session', 'display_name', 'phone_number', 'is_sandbox', 'question', 'status', 'faq', 'answer')},
            {
                'business': self.cafe.pk, 'chat_session': self.alice.pk, 'display_name': 'Alice',
                'phone_number': '+6591234567', 'is_sandbox': False, 'question': 'Are you halal?',
                'status': 'answered', 'faq': self.faq.pk, 'answer': 'No pork or lard.',
            },
        )
        self.assertIsNotNone(answered['answered_time'])
        self.assertEqual((results[self.open_q.pk]['answer'], results[self.open_q.pk]['answered_time']), (None, None))
        self.assertTrue(results[self.sandbox_q.pk]['is_sandbox'])

    def test_answer_follows_the_faq_when_it_is_edited(self):
        self.faq.answer = 'Yes, we are halal-certified.'
        self.faq.save()
        self.client.force_authenticate(self.cafe_user)
        results = {item['id']: item for item in self.client.get(self.list_url).json()['results']}
        self.assertEqual(results[self.answered_q.pk]['answer'], 'Yes, we are halal-certified.')

    def test_status_filter(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids({'status': 'open'}), [self.sandbox_q.pk, self.open_q.pk])
        self.assertEqual(self.ids({'status': 'answered'}), [self.answered_q.pk])
        self.assertEqual(self.ids({'status': 'dismissed'}), [self.dismissed_q.pk])

    def test_sandbox_filter(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids({'sandbox': 'only'}), [self.sandbox_q.pk])
        self.assertEqual(self.ids({'sandbox': 'exclude', 'status': 'open'}), [self.open_q.pk])
        self.assertEqual(len(self.ids({'sandbox': 'include'})), 4)

    def test_ordering(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids({'ordering': 'created_time'})[0], self.open_q.pk)

    def test_pagination(self):
        self.client.force_authenticate(self.cafe_user)
        body = self.client.get(self.list_url, {'page_size': 3}).json()
        self.assertEqual((body['count'], body['total_pages'], len(body['results']), body['has_next']), (4, 2, 3, True))
        self.assertEqual(self.client.get(self.list_url, {'page': 9}).status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_filters_return_400(self):
        self.client.force_authenticate(self.cafe_user)
        for params in ({'status': 'closed'}, {'sandbox': 'yes'}, {'ordering': 'question'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.list_url, params).status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_only(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.post(self.list_url, {'question': 'Q?', 'chat_session': self.alice.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class AnswerQuestionAPITests(QuestionAPITestCase):
    def setUp(self):
        self.item = self.make_question(self.alice, 'Do you have oat milk?')
        self.client.force_authenticate(self.cafe_user)

    def answer(self, item=None, **data):
        return self.client.post(self.answer_url(item or self.item), {'answer': 'Yes, for 50 cents more.', **data}, format='json')

    def test_answering_saves_an_faq_replies_in_the_chat_and_closes_the_question(self):
        before, version = self.alice.last_chat_time, self.alice.version
        response = self.answer()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, QuestionStatus.ANSWERED)
        self.assertLess(timezone.now() - self.item.answered_time, timedelta(seconds=5))
        faq = FAQ.objects.get(business=self.cafe)
        self.assertEqual((faq.question, faq.answer, self.item.faq), ('Do you have oat milk?', 'Yes, for 50 cents more.', faq))
        self.assertEqual(
            {k: response.data[k] for k in ('id', 'status', 'faq', 'answer')},
            {'id': self.item.pk, 'status': 'answered', 'faq': faq.pk, 'answer': 'Yes, for 50 cents more.'},
        )
        self.alice.refresh_from_db()
        [message] = self.alice.chat_message_json
        self.assertEqual(message['message'], 'Regarding your previous question about "Do you have oat milk?": Yes, for 50 cents more.')
        self.assertEqual(message['sent_by'], 'business-manual')
        validate_chat_messages(self.alice.chat_message_json)
        self.assertGreater(self.alice.last_chat_time, before)
        self.assertEqual(self.alice.version, version + 1)  # messaging-service sees the chat changed

    def test_reworded_question(self):
        response = self.answer(question='  Do you have  oat milk for coffee? ')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(FAQ.objects.get().question, 'Do you have oat milk for coffee?')
        self.item.refresh_from_db()
        self.assertEqual(self.item.question, 'Do you have oat milk for coffee?')
        self.alice.refresh_from_db()
        self.assertIn('about "Do you have oat milk for coffee?"', self.alice.chat_message_json[-1]['message'])

    def test_existing_faq_with_the_same_question_gets_the_new_answer(self):
        faq = FAQ.objects.create(business=self.cafe, question='Do you have oat milk?', answer='Not yet.')
        self.assertEqual(self.answer().status_code, status.HTTP_200_OK)
        faq.refresh_from_db()
        self.assertEqual((FAQ.objects.count(), faq.answer), (1, 'Yes, for 50 cents more.'))

    def test_the_faq_is_editable_afterwards(self):
        self.answer()
        faq = FAQ.objects.get()
        response = self.client.patch(reverse('product_app:faq-detail', args=[faq.pk]), {'answer': 'Yes, free!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listed = self.client.get(self.list_url).json()['results'][0]
        self.assertEqual(listed['answer'], 'Yes, free!')

    def test_answers_real_and_sandbox_chats(self):
        sandbox_item = self.make_question(self.sandbox, 'Parking?')
        self.assertEqual(self.answer(sandbox_item, answer='Street parking only.').status_code, status.HTTP_200_OK)
        self.sandbox.refresh_from_db()
        self.assertEqual(self.sandbox.chat_message_json[-1]['message'], answer_message('Parking?', 'Street parking only.'))

    def test_validation(self):
        cases = {
            'missing answer': {'answer': None},
            'blank answer': {'answer': '   '},
            'answer too long': {'answer': 'x' * (ANSWER_MAX_LENGTH + 1)},
            'blank question': {'question': '  '},
            'question too long': {'question': 'x' * (FAQ_QUESTION_MAX_LENGTH + 1)},
        }
        for label, data in cases.items():
            with self.subTest(label):
                payload = {'answer': 'Yes.', **data}
                payload = {k: v for k, v in payload.items() if v is not None}
                response = self.client.post(self.answer_url(self.item), payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, QuestionStatus.OPEN)
        self.assertFalse(FAQ.objects.exists())

    def test_the_longest_answer_fits_in_a_chat_message(self):
        longest = answer_message('q' * FAQ_QUESTION_MAX_LENGTH, 'a' * ANSWER_MAX_LENGTH)
        self.assertEqual(len(longest), CHAT_MESSAGE_MAX_LENGTH)
        response = self.answer(answer='a' * ANSWER_MAX_LENGTH, question='q' * FAQ_QUESTION_MAX_LENGTH)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_only_open_questions_can_be_answered(self):
        self.assertEqual(self.answer().status_code, status.HTTP_200_OK)
        response = self.answer(answer='Again.')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)
        dismissed = self.make_question(self.alice, 'Hiring?', status=QuestionStatus.DISMISSED)
        self.assertEqual(self.answer(dismissed).status_code, status.HTTP_400_BAD_REQUEST)
        self.alice.refresh_from_db()
        self.assertEqual(len(self.alice.chat_message_json), 1)  # only the first answer was sent

    def test_all_or_nothing(self):
        with patch('chat_app.questions.append_chat_message', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                answer_question(self.item, 'Yes.')
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, QuestionStatus.OPEN)
        self.assertFalse(FAQ.objects.exists())

    def test_permissions(self):
        florist_item = self.make_question(self.rose_chat, 'Sunflowers?')
        self.assertEqual(self.answer(florist_item).status_code, status.HTTP_403_FORBIDDEN)
        missing = self.client.post(reverse('chat_app:question-answer', args=[999999]), {'answer': 'Yes.'}, format='json')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.answer().status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(None)
        self.assertEqual(self.answer().status_code, status.HTTP_401_UNAUTHORIZED)
        florist_item.refresh_from_db()
        self.assertEqual(florist_item.status, QuestionStatus.OPEN)
        self.assertFalse(FAQ.objects.exists())

    def test_other_methods_not_allowed(self):
        self.assertEqual(self.client.get(self.answer_url(self.item)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class DismissQuestionAPITests(QuestionAPITestCase):
    def setUp(self):
        self.item = self.make_question(self.alice, 'Are you hiring?')
        self.client.force_authenticate(self.cafe_user)

    def test_dismissing_closes_it_without_replying(self):
        response = self.client.post(self.dismiss_url(self.item))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data['status'], response.data['answered_time']), ('dismissed', None))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, QuestionStatus.DISMISSED)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.chat_message_json, [])
        self.assertFalse(FAQ.objects.exists())

    def test_only_open_questions_can_be_dismissed(self):
        self.client.post(self.dismiss_url(self.item))
        self.assertEqual(self.client.post(self.dismiss_url(self.item)).status_code, status.HTTP_400_BAD_REQUEST)
        answered = self.make_question(self.alice, 'Halal?', status=QuestionStatus.ANSWERED, answered_time=timezone.now())
        self.assertEqual(self.client.post(self.dismiss_url(answered)).status_code, status.HTTP_400_BAD_REQUEST)

    def test_permissions(self):
        florist_item = self.make_question(self.rose_chat, 'Sunflowers?')
        self.assertEqual(self.client.post(self.dismiss_url(florist_item)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(reverse('chat_app:question-dismiss', args=[999999])).status_code, status.HTTP_404_NOT_FOUND
        )
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.post(self.dismiss_url(self.item)).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.dismiss_url(self.item)).status_code, status.HTTP_401_UNAUTHORIZED)
        florist_item.refresh_from_db()
        self.assertEqual(florist_item.status, QuestionStatus.OPEN)


class SampleUnansweredQuestionFixtureTests(TestCase):
    fixtures = [
        'sample_business_configurations', 'sample_faqs', 'sample_chat_configurations', 'sample_chat_sessions',
        'sample_unanswered_questions',
    ]

    def test_fixture_is_valid(self):
        self.assertEqual(UnansweredQuestion.objects.filter(business_id=7).count(), 2)  # 7: Business Test, kept from production (testansera)
        questions = UnansweredQuestion.objects.exclude(business_id=7)
        self.assertEqual(questions.count(), 5)
        for item in questions:
            with self.subTest(question=item.question):
                item.full_clean()  # loaddata skips validation
                self.assertEqual(item.business_id, 2)  # Bloom & Twine Florist Studio
                self.assertGreaterEqual(item.chat_session.last_chat_time, item.created_time)
        self.assertEqual(
            sorted(questions.values_list('status', flat=True)), ['answered', 'answered', 'dismissed', 'open', 'open']
        )

    def test_answered_questions_are_faqs_and_were_replied_to_in_the_chat(self):
        for item in UnansweredQuestion.objects.filter(status=QuestionStatus.ANSWERED):
            with self.subTest(question=item.question):
                self.assertEqual(item.faq.question, item.question)
                replies = [m for m in item.chat_session.chat_message_json if m['sent_by'] == 'business-manual']
                self.assertIn(answer_message(item.question, item.faq.answer), [m['message'] for m in replies])
