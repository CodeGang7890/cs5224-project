"""
URL configuration for the configuration service.

- /admin/                 Django admin
- /api/auth/              auth_app: JWT login/refresh/verify/logout, current user profile
- /api/configuration/     configuration_app API routes
- /api/products/, /api/faqs/   product_app CRUD APIs (login required)
- /api/schema/            OpenAPI 3 schema (YAML/JSON)
- /api/docs/              Swagger UI
- /api/redoc/             ReDoc UI
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('auth_app.urls')),
    path('api/configuration/', include('configuration_app.urls')),
    path('api/', include('product_app.urls')),
    # API docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
