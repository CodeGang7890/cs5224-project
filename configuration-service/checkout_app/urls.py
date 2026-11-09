from django.urls import path

from . import views

app_name = 'checkout_app'

# Mounted under /api/ in config/urls.py.
urlpatterns = [
    path('orders/', views.OrderItemListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', views.OrderItemDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/complete/', views.OrderItemCompleteView.as_view(), name='order-complete'),
    path('schedules/', views.ScheduleItemListView.as_view(), name='schedule-list'),
    path('schedules/<int:pk>/', views.ScheduleItemDetailView.as_view(), name='schedule-detail'),
    path('schedules/<int:pk>/complete/', views.ScheduleItemCompleteView.as_view(), name='schedule-complete'),
    # The invoice / receipt PDFs (checkout_app/documents.py).
    path('orders/<int:pk>/invoice/', views.OrderItemDocumentView.as_view(), {'kind': 'invoice'}, name='order-invoice'),
    path('orders/<int:pk>/receipt/', views.OrderItemDocumentView.as_view(), {'kind': 'receipt'}, name='order-receipt'),
    path('schedules/<int:pk>/invoice/', views.ScheduleItemDocumentView.as_view(), {'kind': 'invoice'}, name='schedule-invoice'),
    path('schedules/<int:pk>/receipt/', views.ScheduleItemDocumentView.as_view(), {'kind': 'receipt'}, name='schedule-receipt'),
]
