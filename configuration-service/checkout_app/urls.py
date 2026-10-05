from django.urls import path

from . import views

app_name = 'checkout_app'

# Mounted under /api/orders/ in config/urls.py.
urlpatterns = [
    path('', views.OrderItemListView.as_view(), name='order-list'),
    path('<int:pk>/', views.OrderItemDetailView.as_view(), name='order-detail'),
]
