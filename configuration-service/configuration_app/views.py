import hmac
import random

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.business_scope import NO_BUSINESS_MESSAGE

from . import whatsapp
from .models import WhatsAppConfiguration
from .serializers import (
    RandomNumberSerializer,
    VerificationResultSerializer,
    VerifyTokenRequestSerializer,
    WhatsAppConfigurationSerializer,
)

RANDOM_NUMBER_MIN = 1
RANDOM_NUMBER_MAX = 10

NO_WHATSAPP_CONFIGURATION_MESSAGE = 'Your business has not connected WhatsApp yet. Connect it with PUT.'
NO_BUSINESS_WHATSAPP_CONFIGURATION_MESSAGE = 'This business has not connected WhatsApp.'
INTERNAL_API_KEY_HEADER = 'X-Internal-Api-Key'
SIGNATURE_HEADER = 'X-Hub-Signature-256'  # Meta's webhook signature header, forwarded unchanged


class RandomNumberView(APIView):
    """Dummy endpoint used to verify frontend ↔ backend connectivity."""

    # Public: frontend-app's Home tab calls it without logging in.
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        summary='Get a random number',
        description=f'Returns a random integer between {RANDOM_NUMBER_MIN} and {RANDOM_NUMBER_MAX} (inclusive).',
        responses=RandomNumberSerializer,
    )
    def get(self, request: Request) -> Response:
        serializer = RandomNumberSerializer(
            {'value': random.randint(RANDOM_NUMBER_MIN, RANDOM_NUMBER_MAX)}
        )
        return Response(serializer.data)


def get_user_business(request: Request):
    """The logged-in user's business; 403 if the account isn't linked to one."""
    if request.user.business_id is None:
        raise PermissionDenied(NO_BUSINESS_MESSAGE)
    return request.user.business


class WhatsAppConfigurationView(APIView):
    """The logged-in user's business's WhatsApp connection (each business has at most one)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['WhatsApp'],
        summary="Get your business's WhatsApp connection",
        description=(
            'The saved settings, without the secrets (they are never returned; a connection always '
            "has both), plus the `webhook_url` and `verify_token` to enter in Meta's webhook "
            'settings (WhatsApp → Configuration).'
        ),
        responses={
            200: WhatsAppConfigurationSerializer,
            403: OpenApiResponse(description='Your account is not linked to a business.'),
            404: OpenApiResponse(description='Your business has not connected WhatsApp yet.'),
        },
    )
    def get(self, request: Request) -> Response:
        business = get_user_business(request)
        config = WhatsAppConfiguration.objects.filter(business=business).first()
        if config is None:
            raise NotFound(NO_WHATSAPP_CONFIGURATION_MESSAGE)
        return Response(WhatsAppConfigurationSerializer(config).data)

    @extend_schema(
        tags=['WhatsApp'],
        summary='Connect WhatsApp, or change the connection',
        description=(
            'Creates the connection (201) or updates it (200). Use the values from your Meta app: '
            'the Phone Number ID (WhatsApp → API Setup, under the number), the App Secret (App '
            'settings → Basic) and a permanent System User access token. '
            '`access_token` and `app_secret` are required when creating; when updating, leave them '
            'out or blank to keep the saved ones. A `verify_token` is generated on creation. '
            'The credentials are checked with Meta (one Graph API call) before saving, which also '
            'fills in the read-only `display_phone_number` and `verified_name`.'
        ),
        request=WhatsAppConfigurationSerializer,
        responses={
            200: WhatsAppConfigurationSerializer,
            201: WhatsAppConfigurationSerializer,
            400: OpenApiResponse(
                description=(
                    'Invalid fields, a missing secret, a phone number ID used by another business, or '
                    'credentials Meta rejected (the error is under the field it is about).'
                )
            ),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
            503: OpenApiResponse(description="Meta couldn't be reached to check the credentials; nothing was saved."),
        },
        examples=[
            OpenApiExample(
                'Connect',
                value={
                    'phone_number_id': '106540352242922',
                    'access_token': 'EAAG...',
                    'app_secret': '0123456789abcdef0123456789abcdef',
                },
                request_only=True,
            ),
        ],
    )
    def put(self, request: Request) -> Response:
        business = get_user_business(request)
        config = WhatsAppConfiguration.objects.filter(business=business).first()
        serializer = WhatsAppConfigurationSerializer(config, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(business=business)
        return Response(serializer.data, status=status.HTTP_200_OK if config else status.HTTP_201_CREATED)

    @extend_schema(
        tags=['WhatsApp'],
        summary='Disconnect WhatsApp',
        description='Deletes the saved settings. Messages to the webhook are then rejected.',
        responses={
            204: OpenApiResponse(description='Disconnected.'),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
            404: OpenApiResponse(description='Your business has not connected WhatsApp.'),
        },
    )
    def delete(self, request: Request) -> Response:
        business = get_user_business(request)
        deleted, _ = WhatsAppConfiguration.objects.filter(business=business).delete()
        if not deleted:
            raise NotFound(NO_WHATSAPP_CONFIGURATION_MESSAGE)
        return Response(status=status.HTTP_204_NO_CONTENT)


class HasInternalApiKey(permissions.BasePermission):
    """Service-to-service calls: the X-Internal-Api-Key header must match settings.INTERNAL_API_KEY."""

    message = f'Missing or invalid {INTERNAL_API_KEY_HEADER} header.'

    def has_permission(self, request, view) -> bool:
        expected = settings.INTERNAL_API_KEY
        given = request.headers.get(INTERNAL_API_KEY_HEADER, '')
        return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


INTERNAL_API_KEY_PARAMETER = OpenApiParameter(
    INTERNAL_API_KEY_HEADER,
    str,
    location=OpenApiParameter.HEADER,
    required=True,
    description='The shared INTERNAL_API_KEY.',
)
INTERNAL_ERROR_RESPONSES = {
    400: OpenApiResponse(description='Invalid request body.'),
    403: OpenApiResponse(description=f'Missing or invalid {INTERNAL_API_KEY_HEADER} header.'),
    404: OpenApiResponse(description='This business has not connected WhatsApp (or does not exist).'),
}


class InternalWhatsAppView(APIView):
    """Base for the internal WhatsApp checks: API key auth, and the business's connection or 404.

    They answer yes/no, so no secret ever leaves this service: a leaked API key only lets the
    caller check tokens and signatures, not read them.
    """

    authentication_classes: list = []  # not a user: the API key is checked by HasInternalApiKey
    permission_classes = [HasInternalApiKey]

    @staticmethod
    def get_config(business_id: int) -> WhatsAppConfiguration:
        config = WhatsAppConfiguration.objects.filter(business_id=business_id).first()
        if config is None:
            raise NotFound(NO_BUSINESS_WHATSAPP_CONFIGURATION_MESSAGE)
        return config

    @staticmethod
    def result(valid: bool, config: WhatsAppConfiguration) -> Response:
        data = {'valid': valid, 'phone_number_id': config.phone_number_id if valid else None}
        return Response(VerificationResultSerializer(data).data)


class InternalWhatsAppVerifyTokenView(InternalWhatsAppView):
    """For messaging-ingester: Meta's webhook subscription handshake (GET /webhook?hub.verify_token=…)."""

    @extend_schema(
        tags=['Internal'],
        summary="Check a webhook verify token (internal)",
        description=(
            'For messaging-ingester. Meta sends `hub.verify_token` when the owner saves the webhook '
            "in Meta; this says whether it equals the business's `verify_token`. Requires the "
            f'`{INTERNAL_API_KEY_HEADER}` header. Not for browsers.'
        ),
        parameters=[INTERNAL_API_KEY_PARAMETER],
        request=VerifyTokenRequestSerializer,
        responses={200: VerificationResultSerializer, **INTERNAL_ERROR_RESPONSES},
    )
    def post(self, request: Request, business_id: int) -> Response:
        serializer = VerifyTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = self.get_config(business_id)
        valid = whatsapp.verify_token_matches(config.verify_token, serializer.validated_data['verify_token'])
        return self.result(valid, config)


class InternalWhatsAppVerifySignatureView(InternalWhatsAppView):
    """For messaging-ingester: checks that a webhook POST really came from Meta.

    The ingester forwards the webhook as it received it: the raw body as this request's body and
    Meta's X-Hub-Signature-256 header. The body is read as bytes (`request.body`) and never parsed,
    because the signature covers the exact bytes Meta sent.
    """

    @extend_schema(
        tags=['Internal'],
        summary="Check a webhook signature (internal)",
        description=(
            'For messaging-ingester. Forward the webhook unchanged: its raw body as this request\'s '
            f'body (`application/octet-stream`) and its `{SIGNATURE_HEADER}` header. This checks '
            "the HMAC-SHA256 with the business's App Secret. When valid, it also returns the "
            "business's `phone_number_id`, to match against the payload. A missing or malformed "
            f'signature is just `valid: false`. Requires the `{INTERNAL_API_KEY_HEADER}` header. '
            'Not for browsers.'
        ),
        parameters=[
            INTERNAL_API_KEY_PARAMETER,
            OpenApiParameter(
                SIGNATURE_HEADER,
                str,
                location=OpenApiParameter.HEADER,
                description='Meta\'s signature header, unchanged, e.g. "sha256=3f2a…".',
            ),
        ],
        request={'application/octet-stream': OpenApiTypes.BINARY},
        responses={200: VerificationResultSerializer, **INTERNAL_ERROR_RESPONSES},
    )
    def post(self, request: Request, business_id: int) -> Response:
        config = self.get_config(business_id)
        signature = request.headers.get(SIGNATURE_HEADER, '')
        valid = whatsapp.signature_matches(config.app_secret, request.body, signature)
        return self.result(valid, config)
