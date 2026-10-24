from django.urls import path

from . import views

app_name = 'internal'

# Service-to-service routes (X-Internal-Api-Key, no user), mounted under /api/internal/ in config/urls.py.
# No secret is ever returned: the checks answer yes/no, and send uses the token itself.
urlpatterns = [
    # Our Meta app's default webhook (Embedded Signup); business webhooks are the <business_id> ones.
    path('whatsapp/app/verify-token/', views.InternalWhatsAppAppVerifyTokenView.as_view(), name='whatsapp-app-verify-token'),
    path(
        'whatsapp/app/verify-signature/',
        views.InternalWhatsAppAppVerifySignatureView.as_view(),
        name='whatsapp-app-verify-signature',
    ),
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
    path('whatsapp/<int:business_id>/send/', views.InternalWhatsAppSendView.as_view(), name='whatsapp-send'),
]
