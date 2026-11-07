"""Request / response schemas of payment-ingester."""

from typing import Literal

from pydantic import BaseModel, Field


class CustomerSchema(BaseModel):
    """The customer, as collected in the chat (their details' name and email fields)."""

    given_name: str = Field(min_length=1, max_length=100)
    # Xendit's customer email limit (Payment Sessions API).
    email: str = Field(min_length=3, max_length=50)


class CreatePaymentRequest(BaseModel):
    """A payment to create for a placed order or booking (messaging-service, internal key)."""

    kind: Literal['order', 'booking']
    item_id: int = Field(ge=1)
    amount: float = Field(gt=0)
    payment_reference: str = Field(pattern=r'^[0-9a-f]{32}$')
    customer: CustomerSchema
    description: str | None = Field(default=None, max_length=500)
    expiry_minutes: int | None = Field(default=None, strict=True, ge=1, le=2147483647)


class CreatePaymentResponse(BaseModel):
    xendit_payment_id: str
    payment_url: str
