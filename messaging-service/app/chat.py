from fastapi import APIRouter, HTTPException

from . import config, llm
from .schemas import ChatRequest, ChatResponse, ErrorResponse, ValidationErrorResponse

router = APIRouter(tags=['chat'])


@router.post(
    '/chat',
    summary='Send a prompt, get a reply',
    responses={
        422: {'model': ValidationErrorResponse, 'description': 'Invalid request body.'},
        502: {'model': ErrorResponse, 'description': 'Ollama returned an error (e.g. the model is not pulled).'},
        503: {'model': ErrorResponse, 'description': 'Ollama is not reachable.'},
        504: {'model': ErrorResponse, 'description': 'Ollama took too long to answer.'},
    },
)
def chat(body: ChatRequest) -> ChatResponse:
    """Single prompt in, single message out. No conversation history is kept: every request is
    independent. Uses SYSTEM_PROMPT and OLLAMA_MODEL from `app/config.py`.
    """
    # A plain `def` (not `async def`): FastAPI runs it in a thread pool, so the blocking Ollama
    # call doesn't stall the event loop.
    try:
        reply = llm.generate_reply(body.prompt)
    except llm.LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except llm.LLMTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=reply, model=config.LLM_MODEL)
