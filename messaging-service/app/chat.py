from flask.views import MethodView
from flask_smorest import Blueprint, abort

from . import config, llm
from .schemas import ChatRequestSchema, ChatResponseSchema

bp = Blueprint('chat', __name__, description='One-off chat with the LLM (Ollama)')


@bp.route('/chat')
class Chat(MethodView):
    @bp.arguments(ChatRequestSchema)
    @bp.response(200, ChatResponseSchema)
    @bp.alt_response(502, description='Ollama returned an error (e.g. the model is not pulled).')
    @bp.alt_response(503, description='Ollama is not reachable.')
    @bp.alt_response(504, description='Ollama took too long to answer.')
    def post(self, body):
        """Send a prompt, get a reply

        Single prompt in, single message out. No conversation history is kept: every request is
        independent. Uses SYSTEM_PROMPT and OLLAMA_MODEL from `app/config.py`.
        """
        try:
            reply = llm.generate_reply(body['prompt'])
        except llm.LLMUnavailableError as exc:
            abort(503, message=str(exc))
        except llm.LLMTimeoutError as exc:
            abort(504, message=str(exc))
        except llm.LLMError as exc:
            abort(502, message=str(exc))
        return {'reply': reply, 'model': config.OLLAMA_MODEL}
