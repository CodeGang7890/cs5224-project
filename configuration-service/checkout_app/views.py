from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.business_scope import OTHER_BUSINESS_MESSAGE, get_user_business_id
from config.pagination import DetailedPageNumberPagination

from . import documents
from .filters import OrderItemFilter, ScheduleItemFilter
from .models import OrderItem, ScheduleItem
from .serializers import OrderItemSerializer, ScheduleItemSerializer
from .services import StatusChangeError, complete_booking, complete_order

NO_ORDER_MESSAGE = 'No order with this ID.'
NO_SCHEDULE_MESSAGE = 'No booking with this ID.'


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


def _own(model, pk: int, business_id: int, not_found: str):
    item = model.objects.filter(pk=pk).first()
    if item is None:
        raise NotFound(not_found)
    if item.business_id != business_id:  # 403, not 404, like the rest of the API
        raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
    return item


class OrderItemCompleteView(APIView):
    """Marks one of the business's paid orders as completed."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Orders'],
        summary='Mark a paid order as completed',
        description=(
            'Moves the order from `payment_received` to `order_completed` (its products move from on hold '
            'to sold). Any other status returns 400: pending payment → payment received (or failed) is set '
            'by the payment service, not here.'
        ),
        request=None,
        responses={
            200: OrderItemSerializer,
            400: OpenApiResponse(description='The order is not at payment received (`order_status`).'),
            403: OpenApiResponse(description="Another business's order, or your account has no business."),
            404: OpenApiResponse(description='No order with this ID.'),
        },
    )
    def post(self, request, pk: int):
        order = _own(OrderItem, pk, get_user_business_id(request), NO_ORDER_MESSAGE)
        try:
            order = complete_order(order.pk)
        except StatusChangeError as exc:
            raise ValidationError({'order_status': [str(exc)]}) from exc
        return Response(OrderItemSerializer(order).data)


class ScheduleItemCompleteView(APIView):
    """Marks one of the business's paid bookings as completed."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Orders'],
        summary='Mark a paid booking as completed',
        description=(
            'Moves the booking from `payment_received` to `order_completed` (its time stays booked). Any '
            'other status returns 400: pending payment → payment received (or failed) is set by the '
            'payment service, not here.'
        ),
        request=None,
        responses={
            200: ScheduleItemSerializer,
            400: OpenApiResponse(description='The booking is not at payment received (`order_status`).'),
            403: OpenApiResponse(description="Another business's booking, or your account has no business."),
            404: OpenApiResponse(description='No booking with this ID.'),
        },
    )
    def post(self, request, pk: int):
        booking = _own(ScheduleItem, pk, get_user_business_id(request), NO_SCHEDULE_MESSAGE)
        try:
            booking = complete_booking(booking.pk)
        except StatusChangeError as exc:
            raise ValidationError({'order_status': [str(exc)]}) from exc
        booking = ScheduleItem.objects.select_related('service_provider').get(pk=booking.pk)
        return Response(ScheduleItemSerializer(booking).data)


class DocumentsUnavailable(APIException):
    status_code = 503
    default_detail = 'Invoices and receipts are unavailable right now.'
    default_code = 'documents_unavailable'


def _document_response(kind: str, item, what: str) -> HttpResponse:
    """The order's / booking's invoice or receipt PDF, shown in the browser (inline)."""
    try:
        pdf = documents.fetch_pdf(kind, item.business_id, item.payment_reference)
    except documents.DocumentsUnavailable as exc:
        raise DocumentsUnavailable(str(exc)) from exc
    if pdf is None:
        raise NotFound(f'This {what} has no {kind} yet.')
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{kind}-{what}-{item.pk}.pdf"'
    return response


def _document_schema(tag: str, what: str):
    return extend_schema(
        tags=[tag],
        summary=f'The {what}\'s invoice or receipt (PDF)',
        description=(
            f'The PDF processing-service stored for this {what}: the invoice (made when its payment link '
            'was created) or the receipt (made when it was paid).'
        ),
        responses={
            (200, 'application/pdf'): OpenApiResponse(description='The PDF.'),
            403: OpenApiResponse(description=f"Another business's {what}, or your account has no business."),
            404: OpenApiResponse(description=f'No {what} with this ID, or it has no such PDF yet.'),
            503: OpenApiResponse(description='PDFs are not stored in this environment, or Cloud Storage is unreachable.'),
        },
    )


class OrderItemDocumentView(APIView):
    """One of the business's orders' invoice or receipt (`kind`, from the URL)."""

    permission_classes = [IsAuthenticated]

    @_document_schema('Orders', 'order')
    def get(self, request, pk: int, kind: str):
        order = _own(OrderItem, pk, get_user_business_id(request), NO_ORDER_MESSAGE)
        return _document_response(kind, order, 'order')


class ScheduleItemDocumentView(APIView):
    """One of the business's bookings' invoice or receipt (`kind`, from the URL)."""

    permission_classes = [IsAuthenticated]

    @_document_schema('Orders', 'booking')
    def get(self, request, pk: int, kind: str):
        booking = _own(ScheduleItem, pk, get_user_business_id(request), NO_SCHEDULE_MESSAGE)
        return _document_response(kind, booking, 'booking')
