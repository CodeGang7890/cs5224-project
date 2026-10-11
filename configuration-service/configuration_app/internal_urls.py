from django.urls import path

from . import views

app_name = 'internal'

# Service-to-service routes (X-Internal-Api-Key, no user), mounted under /api/internal/ in config/urls.py.
# They only answer yes/no: no secret is ever returned.
urlpatterns = [
    path(
        'whatsapp/<int:business_id>/verify-token/',
        views.InternalWhatsAppVerifyTokenView.as_view(),
        name='whatsapp-verify-token',
    ),
    path(
        'whatsapp/<int:business_id>/verify-signature/',
        views.InternalWhatsAppVerifySignatureView.as_view(),
        name='whatsapp-verify-signature',
    ),
]
