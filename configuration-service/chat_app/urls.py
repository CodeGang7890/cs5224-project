from django.urls import path

from . import views

app_name = 'chat_app'

# API routes for this app, mounted under /api/chat/ in config/urls.py.
urlpatterns = [
    path('', views.ChatView.as_view(), name='chat'),
]
