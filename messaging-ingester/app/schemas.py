from http import HTTPStatus

from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str = Field(examples=['messaging-ingester is running'])


class WebhookAck(BaseModel):
    published: int = Field(description='How many customer messages were published to Pub/Sub.', examples=[1])


class ErrorResponse(BaseModel):
    code: int = Field(examples=[503])
    status: str = Field(examples=['Service Unavailable'])
    message: str = Field(examples=['Could not reach configuration-service.'])


class ValidationErrorResponse(BaseModel):
    code: int = Field(examples=[422])
    status: str = Field(examples=[HTTPStatus(422).phrase])
    errors: dict[str, dict[str, list[str]]] = Field(
        description='Error messages by location (e.g. `query`), then by field.',
        examples=[{'query': {'hub.challenge': ['Field required']}}],
    )
