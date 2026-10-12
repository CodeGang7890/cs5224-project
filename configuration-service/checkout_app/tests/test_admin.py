from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from auth_app.models import BusinessUser
from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider

from ..models import OrderItem, ScheduleItem
from .test_models import VALID_ORDER_DATA


class PaymentReferenceAdminTests(TestCase):
    """The payment reference is shown (read only) in the admin lists and pages, and searchable."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = BusinessUser.objects.create_superuser(username='admin', password='123')
        business = BusinessConfiguration.objects.create(business_name='Snap', location='Singapore')
        cls.order = OrderItem.objects.create(business=business, order_data=VALID_ORDER_DATA)
        provider = ServiceProvider.objects.create(business=business, name='Mei')
        service = Service.objects.create(business=business, name='Portrait', price='180.00', duration_minutes=60)
        start = timezone.now() + timedelta(days=7)
        cls.booking = ScheduleItem.objects.create(
            business=business, service=service, service_provider=provider, start_time=start,
            end_time=start + timedelta(minutes=60), blocked_until=start + timedelta(minutes=60),
            schedule_data={
                'service': {'service_id': service.pk, 'name': 'Portrait', 'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 0},
                'details': {},
            },
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_shown_in_the_lists_and_searchable(self):
        for item, name in ((self.order, 'orderitem'), (self.booking, 'scheduleitem')):
            with self.subTest(model=name):
                url = reverse(f'admin:checkout_app_{name}_changelist')
                response = self.client.get(url)
                self.assertContains(response, 'column-payment_reference')
                self.assertContains(response, item.payment_reference)
                found = self.client.get(url, {'q': item.payment_reference})
                self.assertContains(found, item.payment_reference)
                self.assertNotContains(self.client.get(url, {'q': 'f' * 32}), item.payment_reference)

    def test_shown_read_only_on_the_page(self):
        for item, name in ((self.order, 'orderitem'), (self.booking, 'scheduleitem')):
            with self.subTest(model=name):
                response = self.client.get(reverse(f'admin:checkout_app_{name}_change', args=[item.pk]))
                self.assertContains(response, item.payment_reference)
                self.assertNotContains(response, 'name="payment_reference"')  # not an input: read only
