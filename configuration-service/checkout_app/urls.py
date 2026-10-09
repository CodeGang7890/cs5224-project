from django.urls import path

from . import views

app_name = 'checkout_app'

# Mounted under /api/ in config/urls.py.
urlpatterns = [
    path('orders/', views.OrderItemListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', views.OrderItemDetailView.as_view(), name='order-detail'),
    path('schedules/', views.ScheduleItemListView.as_view(), name='schedule-list'),
    path('schedules/<int:pk>/', views.ScheduleItemDetailView.as_view(), name='schedule-detail'),
]
