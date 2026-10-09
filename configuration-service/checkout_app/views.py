from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated

from auth_app.business_scope import NO_BUSINESS_MESSAGE, OTHER_BUSINESS_MESSAGE
from config.pagination import DetailedPageNumberPagination

from .filters import OrderItemFilter, ScheduleItemFilter
from .models import OrderItem, ScheduleItem
from .serializers import OrderItemSerializer, ScheduleItemSerializer

NO_ORDER_MESSAGE = 'No order with this ID.'
NO_SCHEDULE_MESSAGE = 'No booking with this ID.'


def get_user_business_id(request) -> int:
    """The logged-in user's business ID; 403 if the account isn't linked to one."""
    if request.user.business_id is None:
        raise PermissionDenied(NO_BUSINESS_MESSAGE)
    return request.user.business_id


class OrderItemListView(generics.ListAPIView):
    """The logged-in user's business's orders. Read only: orders come from confirmed chats."""

    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DetailedPageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderItemFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return OrderItem.objects.none()
        return OrderItem.objects.filter(business_id=get_user_business_id(self.request)).order_by('-created_time', '-id')

    @extend_schema(
        tags=['Orders'],
        summary="List your business's orders (filter, sort, paginate)",
        description=(
            'Orders placed by customers confirming in a chat, newest first, including sandbox (test) '
            'orders unless `sandbox=exclude`. Each has `order_data` (items and customer details), '
            '`order_status` and `total`. A page past the end returns 404; an invalid filter returns 400.'
        ),
        parameters=[OpenApiParameter('page_size', int, description='Items per page (default 20, max 100).')],
        responses={
            200: OrderItemSerializer(many=True),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class OrderItemDetailView(generics.RetrieveAPIView):
    """One order of the logged-in user's business."""

    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]
    queryset = OrderItem.objects.all()

    def get_object(self):
        business_id = get_user_business_id(self.request)
        order = OrderItem.objects.filter(pk=self.kwargs['pk']).first()
        if order is None:
            raise NotFound(NO_ORDER_MESSAGE)
        if order.business_id != business_id:  # 403, not 404, like the rest of the API
            raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
        return order

    @extend_schema(
        tags=['Orders'],
        summary='Get one of your orders',
        responses={
            200: OrderItemSerializer,
            403: OpenApiResponse(description="Another business's order, or your account has no business."),
            404: OpenApiResponse(description='No order with this ID.'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ScheduleItemListView(generics.ListAPIView):
    """The logged-in user's business's bookings. Read only: bookings come from confirmed chats."""

    serializer_class = ScheduleItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DetailedPageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ScheduleItemFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return ScheduleItem.objects.none()
        return (
            ScheduleItem.objects.filter(business_id=get_user_business_id(self.request))
            .select_related('service_provider')
            .order_by('-start_time', '-id')
        )

    @extend_schema(
        tags=['Orders'],
        summary="List your business's bookings (filter, sort, paginate)",
        description=(
            'Service bookings (time slots) placed by customers confirming in a chat, latest start first, '
            'including sandbox (test) bookings unless `sandbox=exclude`. Each has `schedule_data` (the '
            'service and customer details), the times, `order_status` and `total`. A page past the end '
            'returns 404; an invalid filter returns 400.'
        ),
        parameters=[OpenApiParameter('page_size', int, description='Items per page (default 20, max 100).')],
        responses={
            200: ScheduleItemSerializer(many=True),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ScheduleItemDetailView(generics.RetrieveAPIView):
    """One booking of the logged-in user's business."""

    serializer_class = ScheduleItemSerializer
    permission_classes = [IsAuthenticated]
    queryset = ScheduleItem.objects.all()

    def get_object(self):
        business_id = get_user_business_id(self.request)
        booking = ScheduleItem.objects.select_related('service_provider').filter(pk=self.kwargs['pk']).first()
        if booking is None:
            raise NotFound(NO_SCHEDULE_MESSAGE)
        if booking.business_id != business_id:  # 403, not 404, like the rest of the API
            raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
        return booking

    @extend_schema(
        tags=['Orders'],
        summary='Get one of your bookings',
        responses={
            200: ScheduleItemSerializer,
            403: OpenApiResponse(description="Another business's booking, or your account has no business."),
            404: OpenApiResponse(description='No booking with this ID.'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
