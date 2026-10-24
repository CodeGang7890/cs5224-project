import hmac
import random

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.business_scope import NO_BUSINESS_MESSAGE

from . import account_updates, embedded_signup, meta_api, whatsapp
from .models import WhatsAppConfiguration, WhatsAppConnectionMethod
from .serializers import (
    AccountUpdatesRequestSerializer,
    AccountUpdatesResultSerializer,
    EmbeddedSignupSerializer,
    MetaUnavailable,
    RandomNumberSerializer,
    SendMessageRequestSerializer,
    SendMessageResponseSerializer,
    VerificationResultSerializer,
    VerifyTokenRequestSerializer,
    WhatsAppConfigurationSerializer,
)

RANDOM_NUMBER_MIN = 1
RANDOM_NUMBER_MAX = 10

PHONE_NUMBER_TAKEN_MESSAGE = 'This phone number ID is already connected to another business.'
NO_WHATSAPP_CONFIGURATION_MESSAGE = 'Your business has not connected WhatsApp yet. Connect it with Facebook.'
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
            'The connected number (as Meta verified it) and how it was connected. Connect with '
            '`POST …/embedded-signup/`. The secrets and webhook details are never returned.'
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
        config = WhatsAppConfiguration.objects.filter(business=business).first()
        if config is None:
            raise NotFound(NO_WHATSAPP_CONFIGURATION_MESSAGE)
        if config.connection_method == WhatsAppConnectionMethod.EMBEDDED_SIGNUP:
            embedded_signup.unsubscribe(config.waba_id, config.access_token, config.app_secret)
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmbeddedSignupUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Connecting with Facebook is not set up on this server. Enter your WhatsApp details instead.'
    default_code = 'embedded_signup_unavailable'


class WhatsAppEmbeddedSignupView(APIView):
    """Connects the business's WhatsApp from Meta's Embedded Signup popup (see embedded_signup.py)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['WhatsApp'],
        summary='Connect WhatsApp with Facebook (Embedded Signup)',
        description=(
            "Send what Meta's Embedded Signup popup returned, straight away (the code expires after 30 "
            'seconds). This exchanges the code for the business\'s token, checks and registers the number, '
            'saves the connection (replacing any existing one) and sets up its webhook automatically, so '
            'there is nothing to enter in Meta. 201 if new, 200 if it replaced a connection.'
        ),
        request=EmbeddedSignupSerializer,
        responses={
            200: WhatsAppConfigurationSerializer,
            201: WhatsAppConfigurationSerializer,
            400: OpenApiResponse(
                description='Invalid fields, a number connected to another business, or Meta refused a step.'
            ),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
            503: OpenApiResponse(description="Embedded Signup isn't configured, or Meta couldn't be reached."),
        },
    )
    def post(self, request: Request) -> Response:
        business = get_user_business(request)
        serializer = EmbeddedSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            config, created = embedded_signup.connect(business, data['code'], data['waba_id'], data['phone_number_id'])
        except embedded_signup.EmbeddedSignupNotConfigured as exc:
            raise EmbeddedSignupUnavailable() from exc
        except embedded_signup.PhoneNumberTaken as exc:
            raise ValidationError({'phone_number_id': [PHONE_NUMBER_TAKEN_MESSAGE]}) from exc
        except meta_api.MetaSignupError as exc:
            raise ValidationError({'non_field_errors': [str(exc)]}) from exc
        except meta_api.MetaUnavailableError as exc:
            raise MetaUnavailable() from exc
        return Response(
            WhatsAppConfigurationSerializer(config).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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


class InternalWhatsAppSendView(InternalWhatsAppView):
    """For messaging-service: sends a reply to a customer on WhatsApp, from the business's number.

    The access token never leaves this service: the caller gives the business, the customer's
    number and the text; this calls Meta's Graph API (meta_api.send_text_message).
    """

    @extend_schema(
        tags=['Internal'],
        summary='Send a WhatsApp message (internal)',
        description=(
            "For messaging-service. Sends `text` to the customer `to` from the business's WhatsApp number, "
            "through Meta's Graph API (`META_GRAPH_API_URL`; locally, mock_whatsapp). 502 if Meta refuses "
            f'it, 503 if Meta can\'t be reached (retry later). Requires the `{INTERNAL_API_KEY_HEADER}` header. '
            'Not for browsers.'
        ),
        parameters=[INTERNAL_API_KEY_PARAMETER],
        request=SendMessageRequestSerializer,
        responses={
            200: SendMessageResponseSerializer,
            **INTERNAL_ERROR_RESPONSES,
            502: OpenApiResponse(description='Meta refused the message.'),
            503: OpenApiResponse(description="Meta couldn't be reached."),
        },
    )
    def post(self, request: Request, business_id: int) -> Response:
        serializer = SendMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = self.get_config(business_id)
        try:
            message_id = meta_api.send_text_message(
                config.phone_number_id, config.access_token, config.app_secret,
                serializer.validated_data['to'], serializer.validated_data['text'],
            )
        except meta_api.MetaSendError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except meta_api.MetaUnavailableError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(SendMessageResponseSerializer({'message_id': message_id}).data)



class InternalWhatsAppAppView(APIView):
    """Base for the checks of our Meta app's own (default) webhook, MESSAGING_INGESTER_PUBLIC_URL/webhook.

    With Embedded Signup, Meta needs a callback URL on our app (App Dashboard → WhatsApp → Configuration)
    for the account-level events that can't be overridden. Business messages still go to each
    business's own URL. 404 while META_APP_SECRET / META_APP_WEBHOOK_VERIFY_TOKEN aren't set.
    """

    authentication_classes: list = []
    permission_classes = [HasInternalApiKey]

    @staticmethod
    def result(valid: bool) -> Response:
        return Response(VerificationResultSerializer({'valid': valid, 'phone_number_id': None}).data)


class InternalWhatsAppAppVerifyTokenView(InternalWhatsAppAppView):
    @extend_schema(
        tags=['Internal'],
        summary="Check our app webhook's verify token (internal)",
        description=(
            "For messaging-ingester: Meta's handshake for our app's default webhook. Compares "
            f'`verify_token` with META_APP_WEBHOOK_VERIFY_TOKEN. Requires the `{INTERNAL_API_KEY_HEADER}` header.'
        ),
        parameters=[INTERNAL_API_KEY_PARAMETER],
        request=VerifyTokenRequestSerializer,
        responses={200: VerificationResultSerializer, **INTERNAL_ERROR_RESPONSES},
    )
    def post(self, request: Request) -> Response:
        serializer = VerifyTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not settings.META_APP_WEBHOOK_VERIFY_TOKEN:
            raise NotFound('Our app webhook is not configured (META_APP_WEBHOOK_VERIFY_TOKEN).')
        return self.result(
            whatsapp.verify_token_matches(settings.META_APP_WEBHOOK_VERIFY_TOKEN, serializer.validated_data['verify_token'])
        )


class InternalWhatsAppAppVerifySignatureView(InternalWhatsAppAppView):
    @extend_schema(
        tags=['Internal'],
        summary="Check our app webhook's signature (internal)",
        description=(
            'For messaging-ingester: forward the webhook unchanged (raw body + '
            f'`{SIGNATURE_HEADER}`); checks it with META_APP_SECRET. Requires the `{INTERNAL_API_KEY_HEADER}` header.'
        ),
        parameters=[INTERNAL_API_KEY_PARAMETER],
        request={'application/octet-stream': OpenApiTypes.BINARY},
        responses={200: VerificationResultSerializer, **INTERNAL_ERROR_RESPONSES},
    )
    def post(self, request: Request) -> Response:
        if not settings.META_APP_SECRET:
            raise NotFound('Our app webhook is not configured (META_APP_SECRET).')
        signature = request.headers.get(SIGNATURE_HEADER, '')
        return self.result(whatsapp.signature_matches(settings.META_APP_SECRET, request.body, signature))


class InternalWhatsAppAccountUpdatesView(InternalWhatsAppAppView):
    @extend_schema(
        tags=['Internal'],
        summary="Apply Meta's account_update events (internal)",
        description=(
            "For messaging-ingester: the account_update changes from our app's webhook (already checked "
            'with META_APP_SECRET). Marks the WhatsApp Business account\'s connections disconnected (our app '
            'uninstalled, unshared, account deleted or offboarded) or banned (DISABLED_UPDATE, DISABLE), or '
            'connected again (REINSTATE, ACCOUNT_RECONNECTED); other events change nothing. Idempotent. '
            f'Requires the `{INTERNAL_API_KEY_HEADER}` header.'
        ),
        parameters=[INTERNAL_API_KEY_PARAMETER],
        request=AccountUpdatesRequestSerializer,
        responses={200: AccountUpdatesResultSerializer, 400: OpenApiResponse(description='Invalid body.'),
                   403: OpenApiResponse(description=f'Missing or wrong `{INTERNAL_API_KEY_HEADER}`.')},
    )
    def post(self, request: Request) -> Response:
        serializer = AccountUpdatesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = sum(
            account_updates.apply(account_updates.AccountUpdate(**update))
            for update in serializer.validated_data['updates']
        )
        return Response(AccountUpdatesResultSerializer({'changed': changed}).data)
