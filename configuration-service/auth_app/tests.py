from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from configuration_app.models import BusinessConfiguration

from .models import BusinessUser


class BusinessUserModelTests(TestCase):
    def test_is_the_active_user_model(self):
        self.assertIs(get_user_model(), BusinessUser)

    def test_user_linked_to_business(self):
        business = BusinessConfiguration.objects.create(business_name='Shop', location='Singapore')
        user = BusinessUser.objects.create_user(username='owner', password='pw', business=business)
        self.assertEqual(list(business.users.all()), [user])

    def test_deleting_business_keeps_user(self):
        business = BusinessConfiguration.objects.create(business_name='Shop', location='Singapore')
        user = BusinessUser.objects.create_user(username='owner', password='pw', business=business)
        business.delete()
        user.refresh_from_db()
        self.assertIsNone(user.business)


class AdminSmokeTests(TestCase):
    """Every model's admin list, add and change pages load for a superuser."""

    fixtures = [
        'sample_business_configurations',
        'sample_business_users',
        'sample_products',
        'sample_faqs',
    ]

    def setUp(self):
        admin = BusinessUser.objects.create_superuser(username='admin', password='pw')
        self.client.force_login(admin)

    def test_admin_pages_load(self):
        pages = [
            ('configuration_app', 'businessconfiguration', 1),
            ('auth_app', 'businessuser', 101),
            ('product_app', 'product', 1),
            ('product_app', 'faq', 1),
        ]
        for app, model, pk in pages:
            for url in (
                reverse(f'admin:{app}_{model}_changelist'),
                reverse(f'admin:{app}_{model}_add'),
                reverse(f'admin:{app}_{model}_change', args=[pk]),
            ):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
