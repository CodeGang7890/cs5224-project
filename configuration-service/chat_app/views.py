from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.business_scope import NO_BUSINESS_MESSAGE

from . import llm
from .models import ChatConfiguration
from .serializers import (
    ChatConfigurationSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    ChatSessionSerializer,
)

NO_CHAT_CONFIGURATION_MESSAGE = 'Your business has no chat configuration yet. Create one with PUT.'
SESSION_NEEDS_CONFIGURATION_MESSAGE = (
    'Your business has no chat configuration yet, so a chat session has no Start block to begin at. '
    'Set up the workflow first.'
)

SAMPLE_CONFIG_JSON = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 100, 'position_y': 100},
    {'id': 2, 'next_block_id': 3, 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 300, 'position_y': 100},
    {'id': 3, 'next_block_id': 4, 'block_type': 'DETAILS_COLLECTION_BLOCK', 'position_x': 500, 'position_y': 100},
    {'id': 4, 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 700, 'position_y': 100},
]


class LLMBadGateway(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = 'llm_error'


class LLMUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = 'llm_unavailable'


class LLMTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_code = 'llm_timeout'


class ChatView(APIView):
    """One-off chat with the LLM (Ollama). Moved here from messaging-service for now."""

    # Public, like messaging-service's /chat, so it can be tried from Swagger UI without logging in.
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        tags=['Chat'],
        summary='Send a prompt, get a reply',
        description=(
            'Single prompt in, single message out. No conversation history is kept: every request '
            f'is independent. Uses the `{llm.OLLAMA_MODEL}` model at `{llm.OLLAMA_HOST}` with a '
            'fixed system prompt and hardcoded sampling options (`chat_app/llm.py`). The seed is '
            'fixed, so the same prompt returns the same reply.'
        ),
        request=ChatRequestSerializer,
        responses={
            200: ChatResponseSerializer,
            400: OpenApiResponse(description='Invalid prompt (missing, blank or too long).'),
            502: OpenApiResponse(description='Ollama returned an error (e.g. the model is not pulled).'),
            503: OpenApiResponse(description='Ollama is not reachable.'),
            504: OpenApiResponse(description='Ollama took too long to answer.'),
        },
        examples=[
            OpenApiExample(
                'Prompt',
                value={'prompt': 'Suggest three names for a neighbourhood café.'},
                request_only=True,
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reply = llm.generate_reply(serializer.validated_data['prompt'])
        except llm.LLMUnavailableError as exc:
            raise LLMUnavailable(str(exc)) from exc
        except llm.LLMTimeoutError as exc:
            raise LLMTimeout(str(exc)) from exc
        except llm.LLMError as exc:
            raise LLMBadGateway(str(exc)) from exc
        response = ChatResponseSerializer(
            {'reply': reply, 'model': llm.OLLAMA_MODEL, 'options': llm.OLLAMA_OPTIONS}
        )
        return Response(response.data)


def get_user_business(request: Request):
    """The logged-in user's business; 403 if the account isn't linked to one."""
    if request.user.business_id is None:
        raise PermissionDenied(NO_BUSINESS_MESSAGE)
    return request.user.business


class ChatConfigurationView(APIView):
    """The logged-in user's business's chat configuration (each business has at most one)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat configuration'],
        summary="Get your business's chat configuration",
        responses={
            200: ChatConfigurationSerializer,
            403: OpenApiResponse(description='Your account is not linked to a business.'),
            404: OpenApiResponse(description='Your business has no chat configuration yet.'),
        },
    )
    def get(self, request: Request) -> Response:
        business = get_user_business(request)
        chat_config = ChatConfiguration.objects.filter(business=business).first()
        if chat_config is None:
            raise NotFound(NO_CHAT_CONFIGURATION_MESSAGE)
        return Response(ChatConfigurationSerializer(chat_config).data)

    @extend_schema(
        tags=['Chat configuration'],
        summary="Replace your business's chat flow (config_json)",
        description=(
            'Replaces `config_json`, after checking it with `validate_chat_config`. '
            "Creates the configuration (201) if your business doesn't have one yet. "
            '`id`, `business` and `last_updated` are read-only.'
        ),
        request=ChatConfigurationSerializer,
        responses={
            200: ChatConfigurationSerializer,
            201: ChatConfigurationSerializer,
            400: OpenApiResponse(description='Invalid `config_json`; every problem is listed.'),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
        examples=[
            OpenApiExample(
                'Start → product selection → details collection → confirmation',
                value={'config_json': SAMPLE_CONFIG_JSON},
                request_only=True,
            ),
        ],
    )
    def put(self, request: Request) -> Response:
        business = get_user_business(request)
        chat_config = ChatConfiguration.objects.filter(business=business).first()
        serializer = ChatConfigurationSerializer(chat_config, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(business=business)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK if chat_config else status.HTTP_201_CREATED,
        )


class ChatSessionListView(APIView):
    """Chat sessions of the logged-in user's business."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Chat sessions'],
        summary='Start a chat session with a customer',
        description=(
            'Creates a chat session for your business with the given customer phone number '
            '(unique within your business). The backend sets the rest: `created_time` and '
            '`last_chat_time` are now, `chat_message_json` is empty and `chat_state_id` is the '
            "`id` of the START_BLOCK in your business's chat configuration, which must exist."
        ),
        request=ChatSessionSerializer,
        responses={
            201: ChatSessionSerializer,
            400: OpenApiResponse(
                description=(
                    'Invalid or duplicate phone number, or your business has no chat configuration.'
                ),
            ),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
        examples=[
            OpenApiExample(
                'New customer',
                value={'phone_number': '+6591234567', 'display_name': 'Alice Tan'},
                request_only=True,
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        business = get_user_business(request)
        serializer = ChatSessionSerializer(data=request.data, context={'business': business})
        serializer.is_valid(raise_exception=True)
        chat_config = ChatConfiguration.objects.filter(business=business).first()
        if chat_config is None:
            raise ValidationError({'non_field_errors': [SESSION_NEEDS_CONFIGURATION_MESSAGE]})
        now = timezone.now()
        serializer.save(
            business=business,
            created_time=now,
            last_chat_time=now,
            chat_message_json=[],
            chat_state_id=chat_config.start_block_id,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
