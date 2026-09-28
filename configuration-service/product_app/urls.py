from rest_framework.routers import DefaultRouter

from . import views

app_name = 'product_app'

# Mounted under /api/ in config/urls.py → /api/products/, /api/faqs/
router = DefaultRouter()
router.register('products', views.ProductViewSet, basename='product')
router.register('faqs', views.FAQViewSet, basename='faq')

urlpatterns = router.urls
