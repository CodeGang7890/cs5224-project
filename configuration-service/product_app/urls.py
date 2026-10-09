from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'product_app'

# Mounted under /api/ in config/urls.py → /api/products/, /api/faqs/, /api/weekly-availabilities/, /api/services/,
# /api/businesses/<business_id>/products/, /api/businesses/<business_id>/faqs/
router = DefaultRouter()
router.register('products', views.ProductViewSet, basename='product')
router.register('faqs', views.FAQViewSet, basename='faq')
router.register('weekly-availabilities', views.WeeklyAvailabilityViewSet, basename='weekly-availability')
router.register('services', views.ServiceViewSet, basename='service')

urlpatterns = [
    *router.urls,
    path(
        'businesses/<int:business_id>/products/',
        views.BusinessProductListView.as_view(),
        name='business-product-list',
    ),
    path(
        'businesses/<int:business_id>/faqs/',
        views.BusinessFAQListView.as_view(),
        name='business-faq-list',
    ),
]
