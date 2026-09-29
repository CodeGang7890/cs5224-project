from django.urls import path

from . import views

app_name = 'chat_app'

# API routes for this app, mounted under /api/chat/ in config/urls.py.
urlpatterns = [
    path('', views.ChatView.as_view(), name='chat'),
    path('configuration/', views.ChatConfigurationView.as_view(), name='chat-configuration'),
    path('sessions/', views.ChatSessionListView.as_view(), name='chat-session-list'),
    path('sessions/messages/', views.CustomerMessageView.as_view(), name='customer-message'),
    path('sandbox-sessions/', views.SandboxChatSessionListView.as_view(), name='sandbox-session-list'),
    path('sandbox-sessions/<int:pk>/', views.SandboxChatSessionDetailView.as_view(), name='sandbox-session-detail'),
]
