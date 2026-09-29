from marshmallow import Schema, ValidationError, fields, validate

from . import config


def _not_blank(value: str) -> None:
    if not value.strip():
        raise ValidationError('Must not be blank.')


class MessageSchema(Schema):
    message = fields.String(required=True, metadata={'example': 'Hello, World!'})


class ChatRequestSchema(Schema):
    prompt = fields.String(
        required=True,
        validate=[validate.Length(min=1, max=config.CHAT_PROMPT_MAX_LENGTH), _not_blank],
        metadata={
            'description': f'Your message to the assistant (max {config.CHAT_PROMPT_MAX_LENGTH} characters).',
            'example': 'Suggest three names for a neighbourhood café.',
        },
    )


class ChatResponseSchema(Schema):
    reply = fields.String(required=True, metadata={'description': "The model's answer."})
    model = fields.String(required=True, metadata={'example': config.OLLAMA_MODEL})
