from django.urls import path

from . import views

app_name = 'chat_app'

# API routes for this app, mounted under /api/chat/ in config/urls.py.
urlpatterns = [
    path('configuration/', views.ChatConfigurationView.as_view(), name='chat-configuration'),
    path('configuration/reply-styles/', views.ReplyStyleListView.as_view(), name='reply-style-list'),
    path('sessions/', views.ChatSessionListView.as_view(), name='chat-session-list'),
    path('sandbox-sessions/', views.SandboxChatSessionListView.as_view(), name='sandbox-session-list'),
    path('sandbox-sessions/<int:pk>/', views.SandboxChatSessionDetailView.as_view(), name='sandbox-session-detail'),
    path('sandbox-sessions/<int:pk>/messages/', views.SandboxMessageProxyView.as_view(), name='sandbox-session-message'),
    path('questions/', views.UnansweredQuestionListView.as_view(), name='question-list'),
    path('questions/<int:pk>/answer/', views.UnansweredQuestionAnswerView.as_view(), name='question-answer'),
    path('questions/<int:pk>/dismiss/', views.UnansweredQuestionDismissView.as_view(), name='question-dismiss'),
    path('questions/<int:pk>/add-to-faqs/', views.UnansweredQuestionAddToFaqsView.as_view(), name='question-add-to-faqs'),
]
