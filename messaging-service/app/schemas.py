from http import HTTPStatus

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from . import config


class Message(BaseModel):
    message: str = Field(examples=['Hello, World!'])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')  # unknown fields → 422

    prompt: StrictStr = Field(  # strict: no coercion from numbers etc.
        min_length=1,
        max_length=config.CHAT_PROMPT_MAX_LENGTH,
        description=f'Your message to the assistant (max {config.CHAT_PROMPT_MAX_LENGTH} characters).',
        examples=['Suggest three names for a neighbourhood café.'],
    )

    @field_validator('prompt')
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Must not be blank.')
        return value


class ChatResponse(BaseModel):
    reply: str = Field(description="The model's answer.")
    model: str = Field(examples=[config.OLLAMA_MODEL])


class ErrorResponse(BaseModel):
    code: int = Field(examples=[503])
    status: str = Field(examples=['Service Unavailable'])
    message: str = Field(examples=[f'Could not connect to Ollama at {config.OLLAMA_HOST}.'])


class ValidationErrorResponse(BaseModel):
    code: int = Field(examples=[422])
    status: str = Field(examples=[HTTPStatus(422).phrase])
    errors: dict[str, dict[str, list[str]]] = Field(
        description='Error messages by location (`json` = request body), then by field.',
        examples=[{'json': {'prompt': ['Field required']}}],
    )
