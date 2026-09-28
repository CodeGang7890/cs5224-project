from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, viewsets

from auth_app.business_scope import BusinessFromUrlMixin, BusinessScopedViewSetMixin

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


# --- List by business ID ---------------------------------------------------------------

BUSINESS_LIST_ERRORS = {
    400: OpenApiResponse(description='No business configuration has this ID.'),
    401: OpenApiResponse(description='Not logged in.'),
    403: OpenApiResponse(description="This isn't your business."),
}


def business_list_schema(resource: str, tag: str, serializer):
    return extend_schema(
        tags=[tag],
        summary=f'List a business’s {resource}s',
        description=(
            f'All {resource}s of the business with this `business_id` (paginated). '
            'You can only list your own business.'
        ),
        # For list views drf-spectacular wraps the serializer in the paginated response shape.
        responses={200: serializer, **BUSINESS_LIST_ERRORS},
    )


class BusinessProductListView(BusinessFromUrlMixin, generics.ListAPIView):
    """GET /api/businesses/<business_id>/products/"""

    serializer_class = ProductSerializer

    @business_list_schema('product', 'Products', ProductSerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation has no request/business
            return Product.objects.none()
        return Product.objects.filter(business=self.business).select_related('business')


class BusinessFAQListView(BusinessFromUrlMixin, generics.ListAPIView):
    """GET /api/businesses/<business_id>/faqs/"""

    serializer_class = FAQSerializer

    @business_list_schema('FAQ', 'FAQs', FAQSerializer)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FAQ.objects.none()
        return FAQ.objects.filter(business=self.business).select_related('business')
