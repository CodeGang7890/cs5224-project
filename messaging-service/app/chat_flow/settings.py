"""A business's chat settings: chat_app.ChatConfiguration.for_business(), as a plain object."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BusinessConfiguration, ChatConfiguration
from .constants import BOOKING_STEPS, DEFAULT_REPLY_STYLE
from .validators import default_detail_fields


@dataclass
class ChatSettings:
    """The fields of chat_app.ChatConfiguration the flow reads, with Django's defaults."""

    business: BusinessConfiguration
    product_detail_fields: list[dict] = field(default_factory=default_detail_fields)
    schedule_detail_fields: list[dict] = field(default_factory=default_detail_fields)
    welcome_message: str = ''
    reply_style: str = DEFAULT_REPLY_STYLE
    custom_style: str = ''

    def detail_fields_for(self, step: str) -> list[dict]:
        """The details a step's branch asks for: schedule_detail_fields for the booking steps,
        product_detail_fields otherwise (the order steps, and Start)."""
        return self.schedule_detail_fields if step in BOOKING_STEPS else self.product_detail_fields

    @classmethod
    def for_business(cls, db: Session, business: BusinessConfiguration) -> 'ChatSettings':
        """The business's saved configuration, or the default settings if it has none."""
        saved = db.scalars(select(ChatConfiguration).where(ChatConfiguration.business_id == business.id)).first()
        if saved is None:
            return cls(business=business)
        return cls(
            business=business,
            product_detail_fields=saved.product_detail_fields,
            schedule_detail_fields=saved.schedule_detail_fields,
            welcome_message=saved.welcome_message,
            reply_style=saved.reply_style,
            custom_style=saved.custom_style,
        )
