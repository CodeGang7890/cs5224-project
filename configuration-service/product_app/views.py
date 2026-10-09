from datetime import timedelta

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from auth_app.business_scope import BusinessFromUrlMixin, BusinessScopedViewSetMixin
from checkout_app import schedule

from .models import FAQ, Product, Service, WeeklyAvailability
from .serializers import (
    CalendarQuerySerializer,
    FAQSerializer,
    ProductSerializer,
    ServiceSerializer,
    SlotQuerySerializer,
    SlotsSerializer,
    WeekCalendarSerializer,
    WeeklyAvailabilitySerializer,
)

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


@business_scoped_schema('weekly availability', 'Services', WeeklyAvailabilitySerializer)
class WeeklyAvailabilityViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    """Weekly calendars (e.g. one per photographer) of 15-minute blocks: when services can be booked."""

    queryset = WeeklyAvailability.objects.prefetch_related('services')
    serializer_class = WeeklyAvailabilitySerializer

    @extend_schema(
        tags=['Services'],
        summary="A week of an availability's calendar, with its bookings",
        description=(
            'The weekly template with the bookings of the week containing `week` drawn over it (H: pending '
            'payment, X: paid or completed, including the buffer after each booking), and those bookings. '
            f'Blocks are local times ({settings.SCHEDULE_TIME_ZONE}).'
        ),
        parameters=[CalendarQuerySerializer],
        responses={200: WeekCalendarSerializer, 400: OpenApiResponse(description='Missing or invalid `week`.')},
    )
    @action(detail=True, methods=['get'])
    def calendar(self, request: Request, pk=None) -> Response:
        availability = self.get_object()
        query = CalendarQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        letters, bookings = schedule.week_calendar(availability, query.validated_data['week'])
        return Response(WeekCalendarSerializer({
            'week_start': schedule.week_start(query.validated_data['week']),
            'availability': letters,
            'bookings': [
                {
                    'id': booking.pk,
                    'service': booking.schedule_data['service']['name'],
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                    'blocked_until': booking.blocked_until,
                    'order_status': booking.order_status,
                }
                for booking in bookings
            ],
        }).data)


@business_scoped_schema('service', 'Services', ServiceSerializer)
class ServiceViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.prefetch_related('weekly_availability')
    serializer_class = ServiceSerializer

    @extend_schema(
        tags=['Services'],
        summary='When a service can be booked',
        description=(
            'Every start time (on the 15-minute grid, at least an hour from now) from `date_from` to '
            '`date_to` at which one of the service\'s weekly availabilities has the whole service free, '
            'with no booking (or its buffer) in the way. At most 31 days. Empty for an inactive service.'
        ),
        parameters=[SlotQuerySerializer],
        responses={200: SlotsSerializer, 400: OpenApiResponse(description='Missing or invalid dates.')},
    )
    @action(detail=True, methods=['get'])
    def slots(self, request: Request, pk=None) -> Response:
        service = self.get_object()
        query = SlotQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        date_from, date_to = query.validated_data['date_from'], query.validated_data['date_to']
        date_to = min(date_to, date_from + timedelta(days=schedule.SLOT_SEARCH_DAYS_MAX - 1))
        return Response(SlotsSerializer({
            'date_from': date_from,
            'date_to': date_to,
            'slots': schedule.free_slots(service, date_from, date_to),
        }).data)


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
