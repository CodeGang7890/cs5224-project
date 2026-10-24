from django.urls import path

from . import views

app_name = 'configuration_app'

# API routes for this app, mounted under /api/configuration/ in config/urls.py.
urlpatterns = [
    path('random-number/', views.RandomNumberView.as_view(), name='random-number'),
    path('whatsapp/', views.WhatsAppConfigurationView.as_view(), name='whatsapp-configuration'),
    path(
        'whatsapp/embedded-signup/',
        views.WhatsAppEmbeddedSignupView.as_view(),
        name='whatsapp-embedded-signup',
    ),
]
