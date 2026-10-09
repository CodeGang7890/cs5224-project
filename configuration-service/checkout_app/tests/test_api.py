from datetime import datetime, timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from chat_app.models import ChatSession
from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider

from ..models import OrderItem, OrderStatus
from .test_models import VALID_ORDER_DATA
from .test_schedule import at, book, future_monday

LIST_URL = reverse('checkout_app:order-list')


def detail_url(order_id):
    return reverse('checkout_app:order-detail', args=[order_id])


class OrderAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.cafe_user = BusinessUser.objects.create_user(username='cafe', password='123', business=cls.cafe)
        cls.no_business_user = BusinessUser.objects.create_superuser(username='admin', password='123')
        cls.session = ChatSession.objects.create(business=cls.cafe, phone_number='+6591234567')

        now = timezone.now()
        def order(business, minutes_ago, **fields):
            return OrderItem.objects.create(
                business=business, order_data=VALID_ORDER_DATA, created_time=now - timedelta(minutes=minutes_ago), **fields
            )
        cls.paid = order(cls.cafe, 30, order_status=OrderStatus.PAYMENT_RECEIVED, chat_session=cls.session)
        cls.pending = order(cls.cafe, 10)
        cls.sandbox = order(cls.cafe, 20, is_sandbox=True)
        cls.done = order(cls.cafe, 40, order_status=OrderStatus.ORDER_COMPLETED)
        cls.florist_order = order(cls.florist, 5)


class OrderListAPITests(OrderAPITestCase):
    def ids(self, params=None):
        response = self.client.get(LIST_URL, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return [o['id'] for o in response.json()['results']]

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['detail'], 'Your account is not linked to a business.')

    def test_lists_own_orders_newest_first_including_sandbox(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(LIST_URL)
        body = response.json()
        self.assertEqual([o['id'] for o in body['results']], [self.pending.pk, self.sandbox.pk, self.paid.pk, self.done.pk])
        self.assertEqual(
            {k: body[k] for k in ('count', 'total_pages', 'current_page', 'page_size', 'has_next', 'has_previous')},
            {'count': 4, 'total_pages': 1, 'current_page': 1, 'page_size': 20, 'has_next': False, 'has_previous': False},
        )
        paid = next(o for o in body['results'] if o['id'] == self.paid.pk)
        self.assertEqual(
            set(paid),
            {'id', 'business', 'chat_session', 'is_sandbox', 'order_status', 'order_data', 'total', 'created_time', 'updated_time'},
        )
        self.assertEqual(paid['order_status'], 'payment_received')
        self.assertEqual(paid['chat_session'], self.session.pk)
        self.assertEqual(paid['order_data'], VALID_ORDER_DATA)
        self.assertEqual(paid['total'], '9.10')

    def test_filters(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids({'order_status': 'pending_payment'}), [self.pending.pk, self.sandbox.pk])
        self.assertEqual(self.ids({'order_status': 'order_completed'}), [self.done.pk])
        self.assertEqual(self.ids({'sandbox': 'exclude'}), [self.pending.pk, self.paid.pk, self.done.pk])
        self.assertEqual(self.ids({'sandbox': 'only'}), [self.sandbox.pk])
        self.assertEqual(self.ids({'sandbox': 'only', 'order_status': 'payment_received'}), [])
        after = (self.paid.created_time - timedelta(seconds=1)).isoformat()
        self.assertEqual(self.ids({'created_time_after': after}), [self.pending.pk, self.sandbox.pk, self.paid.pk])

    def test_ordering(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.ids({'ordering': 'created_time'}), [self.done.pk, self.paid.pk, self.sandbox.pk, self.pending.pk])
        self.assertEqual(self.ids({'ordering': 'order_status,-created_time'})[0], self.done.pk)  # alphabetical

    def test_invalid_parameters_return_400(self):
        self.client.force_authenticate(self.cafe_user)
        for params in ({'order_status': 'shipped'}, {'sandbox': 'maybe'}, {'ordering': 'total'}, {'created_time_after': 'yesterday'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(LIST_URL, params).status_code, status.HTTP_400_BAD_REQUEST)

    def test_pagination(self):
        self.client.force_authenticate(self.cafe_user)
        body = self.client.get(LIST_URL, {'page_size': 3, 'page': 2}).json()
        self.assertEqual([o['id'] for o in body['results']], [self.done.pk])
        self.assertEqual((body['total_pages'], body['has_previous'], body['has_next']), (2, True, False))
        self.assertEqual(self.client.get(LIST_URL, {'page': 3, 'page_size': 3}).status_code, status.HTTP_404_NOT_FOUND)

    def test_empty_list(self):
        BusinessUser.objects.create_user(username='new', password='123', business=self.florist)
        self.client.force_authenticate(BusinessUser.objects.get(username='new'))
        self.assertEqual(self.ids({'sandbox': 'only'}), [])

    def test_read_only(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.post(LIST_URL, {'order_data': VALID_ORDER_DATA}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(OrderItem.objects.count(), 5)


class OrderDetailAPITests(OrderAPITestCase):
    def test_requires_authentication(self):
        self.assertEqual(self.client.get(detail_url(self.pending.pk)).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_business_gets_403(self):
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.get(detail_url(self.pending.pk)).status_code, status.HTTP_403_FORBIDDEN)

    def test_gets_own_order(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(detail_url(self.paid.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.paid.pk)
        self.assertEqual(response.json()['total'], '9.10')

    def test_sandbox_order_is_visible(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertTrue(self.client.get(detail_url(self.sandbox.pk)).json()['is_sandbox'])

    def test_other_business_order_returns_403(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(detail_url(self.florist_order.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['detail'], 'You do not have access to this business.')

    def test_unknown_order_returns_404(self):
        self.client.force_authenticate(self.cafe_user)
        response = self.client.get(detail_url(99999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()['detail'], 'No order with this ID.')

    def test_read_only(self):
        self.client.force_authenticate(self.cafe_user)
        url = detail_url(self.pending.pk)
        for method in ('put', 'patch', 'delete'):
            with self.subTest(method):
                response = getattr(self.client, method)(url, {'order_status': 'order_completed'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.order_status, OrderStatus.PENDING_PAYMENT)


SCHEDULE_LIST_URL = reverse('checkout_app:schedule-list')


def schedule_url(booking_id):
    return reverse('checkout_app:schedule-detail', args=[booking_id])


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class ScheduleAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.user = BusinessUser.objects.create_user(username='studio', password='123', business=cls.studio)
        cls.no_business_user = BusinessUser.objects.create_superuser(username='admin', password='123')
        cls.session = ChatSession.objects.create(business=cls.studio, phone_number='+6591234567')
        cls.mei = ServiceProvider.objects.create(business=cls.studio, name='Mei')
        cls.raj = ServiceProvider.objects.create(business=cls.studio, name='Raj')
        cls.portrait = Service.objects.create(business=cls.studio, name='Portrait', price='180.00', duration_minutes=60)
        cls.family = Service.objects.create(business=cls.studio, name='Family', price='250.00', duration_minutes=90, buffer_minutes=30)
        cls.workshop = Service.objects.create(business=cls.florist, name='Workshop', price='50.00', duration_minutes=120)
        theirs = ServiceProvider.objects.create(business=cls.florist, name='Them')
        monday = future_monday()
        cls.monday = monday
        cls.early = book(cls.portrait, cls.mei, at(monday, '09:00'), chat_session=cls.session)
        cls.late = book(cls.family, cls.raj, at(monday + timedelta(days=2), '14:00'), status=OrderStatus.PAYMENT_RECEIVED)
        cls.sandbox = book(cls.portrait, cls.mei, at(monday + timedelta(days=1), '10:00'), is_sandbox=True)
        cls.theirs = book(cls.workshop, theirs, at(monday, '09:00'))

    def ids(self, params=None):
        response = self.client.get(SCHEDULE_LIST_URL, params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return [b['id'] for b in response.json()['results']]

    def test_requires_login_and_a_business(self):
        self.assertEqual(self.client.get(SCHEDULE_LIST_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(schedule_url(self.early.pk)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.get(SCHEDULE_LIST_URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_lists_own_bookings_latest_start_first(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.ids(), [self.late.pk, self.sandbox.pk, self.early.pk])
        body = self.client.get(SCHEDULE_LIST_URL).json()
        self.assertEqual(body['total_pages'], 1)
        first = body['results'][0]
        self.assertEqual(set(first), {
            'id', 'business', 'chat_session', 'is_sandbox', 'service', 'service_provider', 'service_provider_name',
            'start_time', 'end_time', 'blocked_until', 'order_status', 'schedule_data', 'total', 'created_time', 'updated_time',
        })
        self.assertEqual((first['service_provider_name'], first['total'], first['order_status']), ('Raj', '250.00', 'payment_received'))
        self.assertEqual(first['schedule_data']['service']['name'], 'Family')
        self.assertEqual(datetime.fromisoformat(first['start_time']), at(self.monday + timedelta(days=2), '14:00'))
        self.assertEqual(datetime.fromisoformat(first['blocked_until']), at(self.monday + timedelta(days=2), '16:00'))

    def test_filters(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.ids({'order_status': 'payment_received'}), [self.late.pk])
        self.assertEqual(self.ids({'sandbox': 'exclude'}), [self.late.pk, self.early.pk])
        self.assertEqual(self.ids({'sandbox': 'only'}), [self.sandbox.pk])
        self.assertEqual(self.ids({'service': self.portrait.pk}), [self.sandbox.pk, self.early.pk])
        self.assertEqual(self.ids({'service_provider': self.raj.pk}), [self.late.pk])
        self.assertEqual(self.ids({'start_time_before': at(self.monday, '23:59').isoformat()}), [self.early.pk])
        self.assertEqual(self.ids({'ordering': 'start_time'}), [self.early.pk, self.sandbox.pk, self.late.pk])
        for params in ({'order_status': 'lost'}, {'sandbox': 'yes'}, {'ordering': 'price'}, {'start_time_after': 'soon'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(SCHEDULE_LIST_URL, params).status_code, status.HTTP_400_BAD_REQUEST)

    def test_detail(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(schedule_url(self.early.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.json()['id'], response.json()['chat_session']), (self.early.pk, self.session.pk))
        self.assertEqual(self.client.get(schedule_url(self.theirs.pk)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(schedule_url(99999)).status_code, status.HTTP_404_NOT_FOUND)

    def test_read_only(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(SCHEDULE_LIST_URL, {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        for method in ('put', 'patch', 'delete'):
            with self.subTest(method):
                response = getattr(self.client, method)(schedule_url(self.early.pk), {}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_a_deleted_provider_shows_as_null(self):
        ServiceProvider.objects.filter(pk=self.raj.pk).delete()
        self.client.force_authenticate(self.user)
        first = self.client.get(SCHEDULE_LIST_URL).json()['results'][0]
        self.assertEqual((first['service_provider'], first['service_provider_name']), (None, None))
