from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import llm
from .serializers import ChatRequestSerializer, ChatResponseSerializer


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
