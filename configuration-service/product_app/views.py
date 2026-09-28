from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets

from auth_app.business_scope import BusinessScopedViewSetMixin

from .models import FAQ, Product
from .serializers import FAQSerializer, ProductSerializer

FORBIDDEN = OpenApiResponse(description="Not your business's record, or your account has no business.")


def business_scoped_schema(resource: str, tag: str, serializer):
    """Swagger docs shared by the business-scoped CRUD viewsets."""
    return extend_schema_view(
        list=extend_schema(tags=[tag], summary=f'List your business’s {resource}s'),
        create=extend_schema(
            tags=[tag],
            summary=f'Create a {resource}',
            description='`business` is optional and defaults to your own business. Any other business returns 403.',
            responses={201: serializer, 403: FORBIDDEN},
        ),
        retrieve=extend_schema(tags=[tag], summary=f'Get a {resource}', responses={200: serializer, 403: FORBIDDEN}),
        update=extend_schema(tags=[tag], summary=f'Replace a {resource}', responses={200: serializer, 403: FORBIDDEN}),
        partial_update=extend_schema(
            tags=[tag], summary=f'Update some fields of a {resource}', responses={200: serializer, 403: FORBIDDEN}
        ),
        destroy=extend_schema(tags=[tag], summary=f'Delete a {resource}', responses={204: None, 403: FORBIDDEN}),
    )


@business_scoped_schema('product', 'Products', ProductSerializer)
class ProductViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


@business_scoped_schema('FAQ', 'FAQs', FAQSerializer)
class FAQViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
