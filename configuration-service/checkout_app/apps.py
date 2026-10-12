from django.apps import AppConfig


class CheckoutAppConfig(AppConfig):
    name = 'checkout_app'
    verbose_name = 'Checkout'

    def ready(self):
        from . import signals  # noqa: F401  (connects the booking signals)
