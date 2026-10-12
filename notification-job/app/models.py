"""Read-only SQLAlchemy models of configuration-service's tables.

configuration-service (Django) owns the schema and every migration: never create or alter tables
from here (the tests' create_all on SQLite is the only exception). Map only the columns the job
needs, as Django defines them; Django's table name is <app_label>_<model name>.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

# Django's BigAutoField. SQLite (tests) only auto-increments INTEGER primary keys.
BigId = BigInteger().with_variant(Integer, 'sqlite')
# Django's JSONField is jsonb on PostgreSQL.
Json = JSON().with_variant(JSONB(), 'postgresql')

# checkout_app.models.OrderStatus
PENDING_PAYMENT = 'pending_payment'
PAYMENT_FAILED = 'payment_failed'


class AwareDateTime(TypeDecorator):
    """Django's DateTimeField with USE_TZ: aware, in UTC (SQLite, in tests, returns naive ones)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class BusinessConfiguration(Base):
    """configuration_app.BusinessConfiguration: a business (tenant)."""

    __tablename__ = 'configuration_app_businessconfiguration'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))

    def __repr__(self) -> str:
        return f'BusinessConfiguration(id={self.id}, business_name={self.business_name!r})'


class ChatSession(Base):
    """chat_app.ChatSession: the chat an order / booking was placed in (the customer's number)."""

    __tablename__ = 'chat_app_chatsession'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    phone_number: Mapped[str] = mapped_column(String(16))  # E.164; empty for some sandbox chats
    display_name: Mapped[str] = mapped_column(String(150))
    is_sandbox: Mapped[bool] = mapped_column(Boolean)


class OrderItem(Base):
    """checkout_app.OrderItem: an order of products."""

    __tablename__ = 'checkout_app_orderitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    is_sandbox: Mapped[bool] = mapped_column(Boolean)
    order_data: Mapped[dict] = mapped_column(Json)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32))
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)

    business: Mapped[BusinessConfiguration] = relationship()
    # Django's order.chat_session (null if the chat was deleted).
    chat_session: Mapped[ChatSession | None] = relationship()


class ScheduleItem(Base):
    """checkout_app.ScheduleItem: a booking of a service."""

    __tablename__ = 'checkout_app_scheduleitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    is_sandbox: Mapped[bool] = mapped_column(Boolean)
    start_time: Mapped[datetime] = mapped_column(AwareDateTime)
    end_time: Mapped[datetime] = mapped_column(AwareDateTime)
    schedule_data: Mapped[dict] = mapped_column(Json)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32))
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)

    business: Mapped[BusinessConfiguration] = relationship()
    chat_session: Mapped[ChatSession | None] = relationship()
