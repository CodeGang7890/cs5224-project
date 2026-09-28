from django.urls import path

from . import views

app_name = 'auth_app'

# Mounted under /api/auth/ in config/urls.py.
urlpatterns = [
    path('token/', views.LoginView.as_view(), name='token-obtain'),
    path('token/refresh/', views.RefreshView.as_view(), name='token-refresh'),
    path('token/verify/', views.VerifyView.as_view(), name='token-verify'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.MeView.as_view(), name='me'),
]
