from datetime import timedelta

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError

from auth_app.business_scope import BusinessFromUrlMixin, BusinessScopedViewSetMixin, IsBusinessMember
from checkout_app import schedule

from .models import BOOKED_LETTERS, FAQ, UNAVAILABLE_WEEK, Product, Service, ServiceProvider, WeeklyAvailability
from .serializers import (
    CalendarQuerySerializer,
    CopyWeekSerializer,
    FAQSerializer,
    ProductSerializer,
    ServiceProviderSerializer,
    ServiceSerializer,
    SetSlotsSerializer,
    SlotQuerySerializer,
    SlotsSerializer,
    WeekCalendarSerializer,
    WeeklyAvailabilitySerializer,
    WeeksChangeSerializer,
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


def _week_letters(row: WeeklyAvailability | None) -> str:
    return row.availability if row else UNAVAILABLE_WEEK


@business_scoped_schema('service provider', 'Services', ServiceProviderSerializer)
class ServiceProviderViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    """Who services are booked with (a photographer, a teacher, a venue...), each with a calendar
    of weeks."""

    queryset = ServiceProvider.objects.prefetch_related('services')
    serializer_class = ServiceProviderSerializer

    @extend_schema(
        tags=['Services'],
        summary="A week of a service provider's calendar, with its bookings",
        description=(
            'The week containing `week`: its letters (O available, U unavailable, H on hold, X booked; all U '
            'if the week has no availability yet) and the bookings taking up any of it, with who booked and '
            f'their status, so a booked block can be explained. Blocks are local times ({settings.SCHEDULE_TIME_ZONE}).'
        ),
        parameters=[CalendarQuerySerializer],
        responses={200: WeekCalendarSerializer, 400: OpenApiResponse(description='Missing or invalid `week`.')},
    )
    @action(detail=True, methods=['get'])
    def calendar(self, request: Request, pk=None) -> Response:
        provider = self.get_object()
        query = CalendarQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        row, bookings = schedule.week_calendar(provider, query.validated_data['week'])
        return Response(WeekCalendarSerializer({
            'service_provider': provider.pk,
            'week': schedule.week_start(query.validated_data['week']),
            'id': row.pk if row else None,
            'availability': _week_letters(row),
            'bookings': [
                {
                    'id': booking.pk,
                    'service': booking.schedule_data['service']['name'],
                    'customer': booking.schedule_data['details'].get('name') if isinstance(
                        booking.schedule_data['details'].get('name'), str
                    ) else None,
                    'details': booking.schedule_data['details'],
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                    'blocked_until': booking.blocked_until,
                    'order_status': booking.order_status,
                    'total': booking.total,
                    'is_sandbox': booking.is_sandbox,
                    'chat_session': booking.chat_session_id,
                }
                for booking in bookings
            ],
        }).data)

    @extend_schema(
        tags=['Services'],
        summary='Open or close time slots over a range of days',
        description=(
            'Sets the blocks from `time_from` to `time_to` on every day from `date_from` to `date_to` whose '
            'weekday is in `weekdays` to O (`available: true`, the default) or U. E.g. the next 2 weeks, '
            'Monday to Friday, 09:00 to 17:00. Booked blocks (H / X) are left as they are (`skipped`); '
            'missing weeks are created. At most 26 weeks.'
        ),
        request=SetSlotsSerializer,
        responses={200: WeeksChangeSerializer, 400: OpenApiResponse(description='Invalid days or times.')},
    )
    @action(detail=True, methods=['post'])
    def slots(self, request: Request, pk=None) -> Response:
        provider = self.get_object()
        body = SetSlotsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        change = schedule.set_slots(
            provider, data['date_from'], data['date_to'], data['weekdays'], data['time_from'], data['time_to'],
            available=data['available'],
        )
        return Response(WeeksChangeSerializer(change).data)

    @extend_schema(
        tags=['Services'],
        summary="Copy a week's availability to the next weeks",
        description=(
            'Copies which blocks are open (O, or booked in the source week) and closed (U) in `source_week` to '
            '`weeks` weeks from `target_week` (default: the week after). Booked blocks in those weeks are left '
            'as they are (`skipped`, where the source week is closed); missing weeks are created.'
        ),
        request=CopyWeekSerializer,
        responses={200: WeeksChangeSerializer, 400: OpenApiResponse(description='Invalid weeks.')},
    )
    @action(detail=True, methods=['post'], url_path='copy-week')
    def copy_week(self, request: Request, pk=None) -> Response:
        provider = self.get_object()
        body = CopyWeekSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        targets = [data['target_week'] + timedelta(weeks=offset) for offset in range(data['weeks'])]
        change = schedule.copy_week(provider, data['source_week'], targets)
        return Response(WeeksChangeSerializer(change).data)


class WeeklyAvailabilityFilter(django_filters.FilterSet):
    service_provider = django_filters.NumberFilter(help_text='Only this service provider\'s weeks (ID).')
    week = django_filters.DateFromToRangeFilter(help_text='Use `week_after` / `week_before` (Mondays, inclusive).')

    class Meta:
        model = WeeklyAvailability
        fields = ['service_provider', 'week']


@extend_schema_view(
    list=extend_schema(tags=['Services'], summary="List your service providers' weeks"),
    create=extend_schema(
        tags=['Services'], summary='Create a week for a service provider',
        description='Only O and U can be set (H and X come from bookings). One per provider and week (a Monday).',
        responses={201: WeeklyAvailabilitySerializer, 403: FORBIDDEN},
    ),
    retrieve=extend_schema(tags=['Services'], summary='Get a week', responses={200: WeeklyAvailabilitySerializer, 403: FORBIDDEN}),
    update=extend_schema(
        tags=['Services'], summary="Replace a week's letters",
        description='Blocks can only change between O and U; booked blocks (H / X) must stay as they are.',
        responses={200: WeeklyAvailabilitySerializer, 403: FORBIDDEN},
    ),
    partial_update=extend_schema(
        tags=['Services'], summary="Change a week's letters",
        description='Blocks can only change between O and U; booked blocks (H / X) must stay as they are.',
        responses={200: WeeklyAvailabilitySerializer, 403: FORBIDDEN},
    ),
    destroy=extend_schema(
        tags=['Services'], summary='Delete a week (only without bookings)',
        responses={204: None, 400: OpenApiResponse(description='The week has bookings.'), 403: FORBIDDEN},
    ),
)
class WeeklyAvailabilityViewSet(viewsets.ModelViewSet):
    """Service providers' weeks. Scoped through the provider's business: listing shows your
    providers' weeks only; another business's week is 403."""

    queryset = WeeklyAvailability.objects.select_related('service_provider')
    serializer_class = WeeklyAvailabilitySerializer
    permission_classes = [IsBusinessMember]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WeeklyAvailabilityFilter

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            return queryset.filter(service_provider__business_id=self.request.user.business_id)
        return queryset

    def perform_destroy(self, instance):
        if any(letter in BOOKED_LETTERS for letter in instance.availability):
            raise ValidationError({'availability': ["This week has bookings (H / X): it can't be deleted."]})
        instance.delete()


@business_scoped_schema('service', 'Services', ServiceSerializer)
class ServiceViewSet(BusinessScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.prefetch_related('service_providers')
    serializer_class = ServiceSerializer

    @extend_schema(
        tags=['Services'],
        summary='When a service can be booked',
        description=(
            'Every start time (on the 15-minute grid, at least an hour from now) from `date_from` to '
            '`date_to` at which one of the service\'s active providers has the whole service available (O) '
            'and nothing booked in its buffer. At most 31 days. Empty for an inactive service.'
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
