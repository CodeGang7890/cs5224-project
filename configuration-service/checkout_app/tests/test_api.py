from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.models import BusinessUser
from chat_app.models import ChatSession
from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider

from .. import documents
from ..models import OrderItem, OrderStatus, ScheduleItem
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
            {
                'id', 'business', 'chat_session', 'is_sandbox', 'order_status', 
                'payment_reference', 'order_data', 'total', 'xendit_payment_id', 'payment_link',
                'created_time', 'updated_time',
            },
        )
        self.assertEqual(paid['payment_reference'], self.paid.payment_reference)
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
        self.assertEqual(self.ids({'payment_reference': self.paid.payment_reference.upper()}), [self.paid.pk])
        self.assertEqual(self.ids({'payment_reference': self.florist_order.payment_reference}), [])  # another business's

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

    def test_invoice_pdf_and_another_business(self):
        self.client.force_authenticate(self.user)
        with patch('checkout_app.documents.fetch_pdf', return_value=b'%PDF') as fetch:
            response = self.client.get(reverse('checkout_app:schedule-invoice', args=[self.early.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        fetch.assert_called_once_with('invoice', self.studio.pk, self.early.payment_reference)
        with patch('checkout_app.documents.fetch_pdf'):
            other = self.client.get(reverse('checkout_app:schedule-receipt', args=[self.theirs.pk]))
        self.assertEqual(other.status_code, status.HTTP_403_FORBIDDEN)

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
        self.assertEqual(
            set(first),
            {
                'id', 'business', 'chat_session', 'is_sandbox', 'service', 'service_provider', 'service_provider_name',
                'start_time', 'end_time', 'blocked_until', 'order_status', 'payment_reference', 'schedule_data', 'total',
                'created_time', 'updated_time', 'xendit_payment_id', 'payment_link',
            },
        )
        self.assertEqual(first['payment_reference'], self.late.payment_reference)
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
        self.assertEqual(self.ids({'payment_reference': self.sandbox.payment_reference}), [self.sandbox.pk])
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

    def test_a_booking_without_a_provider_shows_as_null(self):
        ScheduleItem.objects.filter(service_provider=self.raj).update(service_provider=None)  # e.g. an older row
        self.client.force_authenticate(self.user)
        first = self.client.get(SCHEDULE_LIST_URL).json()['results'][0]
        self.assertEqual((first['service_provider'], first['service_provider_name']), (None, None))


class OrderCompleteAPITests(OrderAPITestCase):
    """POST /api/orders/{id}/complete/: payment received → completed, and nothing else."""

    @staticmethod
    def url(order):
        return reverse('checkout_app:order-complete', args=[order.pk])

    def test_requires_login_and_a_business(self):
        self.assertEqual(self.client.post(self.url(self.paid)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.no_business_user)
        self.assertEqual(self.client.post(self.url(self.paid)).status_code, status.HTTP_403_FORBIDDEN)

    def test_completes_a_paid_order(self):
        self.client.force_authenticate(self.cafe_user)
        before = self.paid.updated_time
        response = self.client.post(self.url(self.paid))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual((response.json()['id'], response.json()['order_status']), (self.paid.pk, 'order_completed'))
        self.paid.refresh_from_db()
        self.assertEqual(self.paid.order_status, OrderStatus.ORDER_COMPLETED)
        self.assertGreater(self.paid.updated_time, before)

    def test_only_from_payment_received(self):
        self.client.force_authenticate(self.cafe_user)
        failed = OrderItem.objects.create(business=self.cafe, order_data=VALID_ORDER_DATA, order_status=OrderStatus.PAYMENT_FAILED)
        for order, label in ((self.pending, 'pending payment'), (self.done, 'order completed'), (failed, 'payment failed')):
            with self.subTest(status=order.order_status):
                response = self.client.post(self.url(order))
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(
                    response.json()['order_status'],
                    [f'Only orders with payment received can be marked as completed (this one is {label}).'],
                )
                status_before = order.order_status
                order.refresh_from_db()
                self.assertEqual(order.order_status, status_before)

    def test_another_business_or_unknown(self):
        self.client.force_authenticate(self.cafe_user)
        self.assertEqual(self.client.post(self.url(self.florist_order)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(reverse('checkout_app:order-complete', args=[99999])).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.url(self.paid)).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_the_products_move_from_on_hold_to_sold(self):
        from product_app.models import Product

        shop = BusinessConfiguration.objects.create(business_name='Shop', location='Singapore')  # no other orders
        self.cafe_user.business = shop
        self.cafe_user.save()
        kopi = Product.objects.create(business=shop, name='Kopi C', price='1.80', total_quantity=10)
        data = {'items': [{'product_id': kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 3}], 'details': {}}
        paid = OrderItem.objects.create(business=shop, order_data=data, order_status=OrderStatus.PAYMENT_RECEIVED)
        kopi = Product.load_stock([Product.objects.get(pk=kopi.pk)])[0]
        self.assertEqual((kopi.quantity_on_hold, kopi.quantity_sold, kopi.quantity_available), (3, 0, 7))
        self.client.force_authenticate(self.cafe_user)
        self.client.post(self.url(paid))
        kopi = Product.load_stock([Product.objects.get(pk=kopi.pk)])[0]
        self.assertEqual((kopi.quantity_on_hold, kopi.quantity_sold, kopi.quantity_available), (0, 3, 7))


@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class ScheduleCompleteAPITests(ScheduleAPITests):
    """POST /api/schedules/{id}/complete/: payment received → completed, and nothing else."""

    @staticmethod
    def url(booking):
        return reverse('checkout_app:schedule-complete', args=[booking.pk])

    def test_completes_a_paid_booking_and_its_time_stays_booked(self):
        from .test_schedule import day_letters

        self.client.force_authenticate(self.user)
        wednesday = self.monday + timedelta(days=2)
        self.assertEqual(day_letters(self.raj, wednesday, '14:00', '15:30'), 'X' * 6)  # its 90 minutes
        response = self.client.post(self.url(self.late))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual((response.json()['order_status'], response.json()['service_provider_name']), ('order_completed', 'Raj'))
        self.late.refresh_from_db()
        self.assertEqual(self.late.order_status, OrderStatus.ORDER_COMPLETED)
        self.assertEqual(day_letters(self.raj, wednesday, '14:00', '15:30'), 'X' * 6)

    def test_only_from_payment_received(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url(self.early))  # pending payment
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['order_status'],
            ['Only bookings with payment received can be marked as completed (this one is pending payment).'],
        )
        self.early.refresh_from_db()
        self.assertEqual(self.early.order_status, OrderStatus.PENDING_PAYMENT)

    def test_another_business_unknown_or_logged_out(self):
        self.assertEqual(self.client.post(self.url(self.late)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(self.url(self.theirs)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(reverse('checkout_app:schedule-complete', args=[99999])).status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_payment_failed(self):
        self.client.force_authenticate(self.user)
        failed = book(self.portrait, self.raj, at(self.monday, '15:00'), status=OrderStatus.PAYMENT_FAILED)
        self.assertEqual(self.ids({'order_status': 'payment_failed'}), [failed.pk])


class OrderDocumentAPITests(OrderAPITestCase):
    """GET /api/orders/{id}/invoice|receipt/: the PDF from Cloud Storage (fetch_pdf patched: no Google)."""

    def url(self, order, kind='receipt'):
        return reverse(f'checkout_app:order-{kind}', args=[order.pk])

    def test_streams_the_pdf_from_the_business_folder(self):
        self.client.force_authenticate(self.cafe_user)
        with patch('checkout_app.documents.fetch_pdf', return_value=b'%PDF-1.4') as fetch:
            response = self.client.get(self.url(self.paid))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline; filename="receipt-order-', response['Content-Disposition'])
        self.assertEqual(response.content, b'%PDF-1.4')
        fetch.assert_called_once_with('receipt', self.cafe.pk, self.paid.payment_reference)

    def test_no_file_yet_is_404(self):
        self.client.force_authenticate(self.cafe_user)
        with patch('checkout_app.documents.fetch_pdf', return_value=None):
            response = self.client.get(self.url(self.pending, 'invoice'))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()['detail'], 'This order has no invoice yet.')

    def test_storage_unavailable_is_503(self):
        self.client.force_authenticate(self.cafe_user)
        with override_settings(GCS_BUCKET=''):   # no bucket: the real fetch_pdf refuses before calling Google
            response = self.client.get(self.url(self.paid))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_other_business_and_unknown(self):
        self.client.force_authenticate(self.cafe_user)
        with patch('checkout_app.documents.fetch_pdf') as fetch:
            self.assertEqual(self.client.get(self.url(self.florist_order)).status_code, status.HTTP_403_FORBIDDEN)
            missing = reverse('checkout_app:order-receipt', args=[999999])
            self.assertEqual(self.client.get(missing).status_code, status.HTTP_404_NOT_FOUND)
        fetch.assert_not_called()

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.url(self.paid)).status_code, status.HTTP_401_UNAUTHORIZED)


class FetchPdfTests(SimpleTestCase):
    """checkout_app.documents.fetch_pdf against a fake Cloud Storage session."""

    def session(self, *statuses):
        responses = [SimpleNamespace(status_code=code, content=b'PDF' if code == 200 else b'') for code in statuses]
        return SimpleNamespace(get=MagicMock(side_effect=responses))

    @override_settings(GCS_BUCKET='bucket')
    def test_tries_the_business_folder_then_the_old_name(self):
        session = self.session(404, 200)
        with patch('checkout_app.documents._get_session', return_value=session):
            self.assertEqual(documents.fetch_pdf('receipt', 7, 'abc'), b'PDF')
        urls = [call.args[0] for call in session.get.call_args_list]
        self.assertEqual(urls, [
            'https://storage.googleapis.com/storage/v1/b/bucket/o/receipts%2F7%2Fabc.pdf?alt=media',
            'https://storage.googleapis.com/storage/v1/b/bucket/o/receipts%2Fabc.pdf?alt=media',
        ])

    @override_settings(GCS_BUCKET='bucket')
    def test_missing_is_none_and_errors_are_unavailable(self):
        with patch('checkout_app.documents._get_session', return_value=self.session(404, 404)):
            self.assertIsNone(documents.fetch_pdf('invoice', 7, 'abc'))
        with patch('checkout_app.documents._get_session', return_value=self.session(403)):
            with self.assertRaises(documents.DocumentsUnavailable):
                documents.fetch_pdf('invoice', 7, 'abc')


# The same token as processing-service's tests/test_document_links.py: both services must agree.
LINK_REFERENCE = '0123456789abcdef0123456789abcdef'
LINK_TOKEN = f'i{LINK_REFERENCE}pRAYtf9KdFjdwQSA'


@override_settings(INTERNAL_API_KEY='test-key')
class SharedDocumentTests(OrderAPITestCase):
    """GET /d/<token>: the PDF behind a short link in a customer's message (no login)."""

    def token(self, order, code='r'):
        return f'{code}{order.payment_reference}{documents.link_signature(code, order.payment_reference, "test-key")}'

    def get(self, token):
        return self.client.get(reverse('shared-document', args=[token]))

    def test_reads_the_token_processing_service_makes(self):
        self.assertEqual(documents.read_link_token(LINK_TOKEN), ('invoice', LINK_REFERENCE))

    def test_serves_the_pdf_without_a_login(self):
        with patch('checkout_app.documents.fetch_pdf', return_value=b'%PDF-1.4') as fetch:
            response = self.get(self.token(self.paid))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response['Content-Disposition'], f'inline; filename="receipt-order-{self.paid.pk}.pdf"')
        self.assertEqual(response.content, b'%PDF-1.4')
        fetch.assert_called_once_with('receipt', self.cafe.pk, self.paid.payment_reference)

    def test_a_bad_or_changed_token_is_404(self):
        good = self.token(self.paid)
        changed_kind = 'i' + good[1:]  # a receipt's signature doesn't open the invoice
        other_order = f'r{self.pending.payment_reference}{good[33:]}'  # nor another order's
        with patch('checkout_app.documents.fetch_pdf') as fetch:
            for token in (changed_kind, other_order, good[:-1], 'x' + good[1:], 'nonsense'):
                self.assertEqual(self.get(token).status_code, 404, token)
            with override_settings(INTERNAL_API_KEY=''):
                self.assertEqual(self.get(good).status_code, 404)
        fetch.assert_not_called()

    def test_no_order_with_that_reference_is_404(self):
        with patch('checkout_app.documents.fetch_pdf') as fetch:
            self.assertEqual(self.get(LINK_TOKEN).status_code, 404)  # signed, but no order has it
        fetch.assert_not_called()

    def test_missing_file_is_404_and_unavailable_storage_503(self):
        with patch('checkout_app.documents.fetch_pdf', return_value=None):
            self.assertEqual(self.get(self.token(self.pending, 'i')).status_code, 404)
        with override_settings(GCS_BUCKET=''):
            self.assertEqual(self.get(self.token(self.pending, 'i')).status_code, 503)

    def test_only_get(self):
        self.assertEqual(self.client.post(reverse('shared-document', args=[self.token(self.paid)])).status_code, 405)
