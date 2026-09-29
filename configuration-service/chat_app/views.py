from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.business_scope import NO_BUSINESS_MESSAGE, OTHER_BUSINESS_MESSAGE

from . import llm
from .constants import SENT_BY_BUSINESS_AUTOMATED, SENT_BY_CUSTOMER
from .models import ChatConfiguration, ChatSession
from .serializers import (
    ChatConfigurationSerializer,
    ChatMessageSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    ChatSessionSerializer,
    CustomerMessageRequestSerializer,
    SandboxChatSessionSerializer,
    SandboxMessageRequestSerializer,
)

NO_CHAT_CONFIGURATION_MESSAGE = 'Your business has no chat configuration yet. Create one with PUT.'
SESSION_NEEDS_CONFIGURATION_MESSAGE = (
    'Your business has no chat configuration yet, so a chat session has no Start block to begin at. '
    'Set up the workflow first.'
)

NO_CHAT_SESSION_MESSAGE = 'No chat session found for this phone number at this business.'
NOT_SANDBOX_MESSAGE = 'This is a real customer chat session; only sandbox chat sessions can be used here.'

SAMPLE_CONFIG_JSON = [
    {'id': 1, 'next_block_id': 2, 'block_type': 'START_BLOCK', 'position_x': 100, 'position_y': 100},
    {'id': 2, 'next_block_id': 3, 'block_type': 'PRODUCT_SELECTION_BLOCK', 'position_x': 300, 'position_y': 100},
    {'id': 3, 'next_block_id': 4, 'block_type': 'DETAILS_COLLECTION_BLOCK', 'position_x': 500, 'position_y': 100},
    {'id': 4, 'next_block_id': None, 'block_type': 'CONFIRMATION_BLOCK', 'position_x': 700, 'position_y': 100},
]


class NotSandboxSession(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = NOT_SANDBOX_MESSAGE
    default_code = 'not_sandbox'


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


def create_chat_session(serializer, business, *, is_sandbox: bool) -> Response:
    """Validates and saves a new session that starts at the business's START_BLOCK."""
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
        is_sandbox=is_sandbox,
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatSessionListView(generics.ListCreateAPIView):
    """Chat sessions of the logged-in user's business: list them, or start a new one."""

    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return ChatSession.objects.none()
        business = get_user_business(self.request)
        sessions = ChatSession.objects.filter(business=business, is_sandbox=False).order_by(
            '-last_chat_time', '-id'
        )
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            sessions = sessions.filter(phone_number=phone_number)
        return sessions

    @extend_schema(
        tags=['Chat sessions'],
        summary="List your business's chat sessions",
        description=(
            'All real (non-sandbox) chat sessions of your business (paginated), most recent chat first, '
            'including each conversation (`chat_message_json`). Filter by `phone_number` to find '
            "one customer's session (at most one, as numbers are unique per business)."
        ),
        parameters=[
            OpenApiParameter(
                'phone_number',
                str,
                description='Only the session with this exact phone number, e.g. `+6591234567` (URL-encode the `+` as `%2B`).',
            ),
        ],
        responses={
            200: ChatSessionSerializer(many=True),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

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
    def post(self, request: Request, *args, **kwargs) -> Response:
        business = get_user_business(request)
        serializer = ChatSessionSerializer(data=request.data, context={'business': business})
        return create_chat_session(serializer, business, is_sandbox=False)


def append_chat_message(session_id: int, message: str, sent_by: str) -> dict:
    """Appends a message (timestamped now) to a session and updates its last_chat_time.

    Row-locked in its own short transaction, so concurrent messages aren't lost. (The lock
    isn't held during the LLM call, which can take a while.)
    """
    with transaction.atomic():
        session = ChatSession.objects.select_for_update().get(pk=session_id)
        now = timezone.now()
        chat_message = {'message': message, 'sent_by': sent_by, 'message_time': now.isoformat()}
        session.chat_message_json.append(chat_message)
        session.last_chat_time = now
        session.save(update_fields=['chat_message_json', 'last_chat_time'])
    return chat_message


def reply_to_customer_message(session: ChatSession, message: str) -> dict:
    """Saves a customer message, gets the assistant's reply from the LLM, saves and returns it.

    The customer message is saved first, so it's kept even if the LLM call fails (502/503/504).
    """
    append_chat_message(session.pk, message, SENT_BY_CUSTOMER)

    # TODO: the core chat logic: use the conversation so far and the business's chat flow
    # (move chat_state_id between blocks, use each block type's prompt) to decide the reply.
    try:
        reply = llm.generate_customer_reply(session.business, message)
    except llm.LLMUnavailableError as exc:
        raise LLMUnavailable(str(exc)) from exc
    except llm.LLMTimeoutError as exc:
        raise LLMTimeout(str(exc)) from exc
    except llm.LLMError as exc:
        raise LLMBadGateway(str(exc)) from exc

    return append_chat_message(session.pk, reply, SENT_BY_BUSINESS_AUTOMATED)


class CustomerMessageView(APIView):
    """A customer sends a message to a business and gets the assistant's reply.

    Used by the Chat Sandbox for now; it will become the WhatsApp webhook later.
    """

    # Public, like a webhook: the customer isn't a logged-in user.
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        tags=['Chat sessions'],
        summary='Send a customer message and get the reply',
        description=(
            'Finds the chat session for `business_id` + `phone_number`, appends the message '
            '(`sent_by: customer`), asks the LLM for a reply, appends the reply '
            '(`sent_by: business-automated`) and returns it. `last_chat_time` is set to the time '
            'of each appended message. `chat_state_id` is not changed yet. The customer message '
            'is kept even if the LLM fails.'
        ),
        request=CustomerMessageRequestSerializer,
        responses={
            200: ChatMessageSerializer,
            400: OpenApiResponse(description='Invalid business ID, phone number or message.'),
            404: OpenApiResponse(description='No chat session for this phone number at this business.'),
            502: OpenApiResponse(description='Ollama returned an error (e.g. the model is not pulled).'),
            503: OpenApiResponse(description='Ollama is not reachable.'),
            504: OpenApiResponse(description='Ollama took too long to answer.'),
        },
        examples=[
            OpenApiExample(
                'Customer message',
                value={'business_id': 1, 'phone_number': '+6591234567', 'message': 'Hi, are you open today?'},
                request_only=True,
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = CustomerMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        session = (
            ChatSession.objects.select_related('business')
            .filter(business_id=data['business_id'], phone_number=data['phone_number'], is_sandbox=False)
            .first()
        )
        if session is None:
            raise NotFound(NO_CHAT_SESSION_MESSAGE)
        return Response(ChatMessageSerializer(reply_to_customer_message(session, data['message'])).data)


def get_own_sandbox_session(request: Request, pk: int) -> ChatSession:
    """The logged-in user's business's sandbox session `pk`.

    403 without a business, 404 if it doesn't exist, 403 if it's another business's (checked
    before the sandbox check, like the rest of the API), 400 if it's a real customer session.
    """
    business = get_user_business(request)
    session = ChatSession.objects.select_related('business').filter(pk=pk).first()
    if session is None:
        raise NotFound('No chat session with this ID.')
    if session.business_id != business.pk:
        raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
    if not session.is_sandbox:
        raise NotSandboxSession()
    return session


class SandboxChatSessionListView(generics.ListCreateAPIView):
    """Sandbox (test) chat sessions of the logged-in user's business: list them, or start one."""

    serializer_class = SandboxChatSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):  # schema generation: no real user
            return ChatSession.objects.none()
        business = get_user_business(self.request)
        return ChatSession.objects.filter(business=business, is_sandbox=True).order_by('-last_chat_time', '-id')

    @extend_schema(
        tags=['Sandbox chat sessions'],
        summary="List your business's sandbox chat sessions",
        description='All sandbox (test) chat sessions of your business (paginated), most recent chat first.',
        responses={
            200: SandboxChatSessionSerializer(many=True),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['Sandbox chat sessions'],
        summary='Start a sandbox chat session',
        description=(
            'Creates a sandbox (test) chat session for your business. `display_name` and '
            '`phone_number` are optional, and a business can have any number of sandbox sessions. '
            'Like real sessions, it starts at the START_BLOCK of your chat configuration, which must '
            'exist, with no messages.'
        ),
        request=SandboxChatSessionSerializer,
        responses={
            201: SandboxChatSessionSerializer,
            400: OpenApiResponse(description='Invalid input, or your business has no chat configuration.'),
            403: OpenApiResponse(description='Your account is not linked to a business.'),
        },
        examples=[
            OpenApiExample('Sandbox chat', value={'display_name': 'sandbox_user'}, request_only=True),
        ],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        business = get_user_business(request)
        serializer = SandboxChatSessionSerializer(data=request.data, context={'business': business})
        return create_chat_session(serializer, business, is_sandbox=True)


class SandboxChatSessionDetailView(APIView):
    """One sandbox chat session of the logged-in user's business."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Sandbox chat sessions'],
        summary='Delete a sandbox chat session',
        description=(
            'Deletes one of your business\'s sandbox chat sessions, with its conversation. '
            'Real customer sessions can\'t be deleted here (400).'
        ),
        responses={
            204: OpenApiResponse(description='Deleted.'),
            400: OpenApiResponse(description='The session is a real customer session, not a sandbox one.'),
            403: OpenApiResponse(description="Another business's session, or your account has no business."),
            404: OpenApiResponse(description='No chat session with this ID.'),
        },
    )
    def delete(self, request: Request, pk: int) -> Response:
        get_own_sandbox_session(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SandboxChatMessageView(APIView):
    """Send a message in one of your sandbox sessions, as the pretend customer."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Sandbox chat sessions'],
        summary='Send a message in a sandbox chat and get the reply',
        description=(
            'Same flow as `POST /api/chat/sessions/messages/`, for one of your sandbox sessions: '
            'appends the message (`sent_by: customer`), asks the LLM for a reply, appends it '
            '(`sent_by: business-automated`) and returns it. The message is kept if the LLM fails.'
        ),
        request=SandboxMessageRequestSerializer,
        responses={
            200: ChatMessageSerializer,
            400: OpenApiResponse(description='Invalid message, or the session is a real customer session.'),
            403: OpenApiResponse(description="Another business's session, or your account has no business."),
            404: OpenApiResponse(description='No chat session with this ID.'),
            502: OpenApiResponse(description='Ollama returned an error (e.g. the model is not pulled).'),
            503: OpenApiResponse(description='Ollama is not reachable.'),
            504: OpenApiResponse(description='Ollama took too long to answer.'),
        },
        examples=[OpenApiExample('Message', value={'message': 'Are you open today?'}, request_only=True)],
    )
    def post(self, request: Request, pk: int) -> Response:
        session = get_own_sandbox_session(request, pk)
        serializer = SandboxMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = reply_to_customer_message(session, serializer.validated_data['message'])
        return Response(ChatMessageSerializer(reply).data)
