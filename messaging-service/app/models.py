"""SQLAlchemy models of the configuration-service (Django) tables the chat flow reads and writes.

configuration-service owns the schema and every migration: this service never creates, alters or
drops tables (the tests' create_all on SQLite is the only exception). Only the columns the chat
flow needs are mapped, as Django defines them; keep them in sync with the Django models. Django's
table names are <app_label>_<model name> (a many-to-many: <app_label>_<model>_<field>). Django
defaults (`default=…`, `auto_now`) don't run here: code that inserts rows sets every column.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# Django's BigAutoField. SQLite (tests) only auto-increments INTEGER primary keys.
BigId = BigInteger().with_variant(Integer, 'sqlite')
# Django's JSONField is jsonb on PostgreSQL.
Json = JSON().with_variant(JSONB(), 'postgresql')


class AwareDateTime(TypeDecorator):
    """Django's DateTimeField with USE_TZ: always aware, stored in UTC. PostgreSQL's timestamptz
    returns aware datetimes; SQLite (tests) naive ones, read back as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError(f'Naive datetime {value!r}: always pass aware datetimes.')
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    @property
    def pk(self) -> int:
        """Django's `pk`, so code ported from configuration-service reads the same."""
        return self.id


class BusinessConfiguration(Base):
    """configuration_app.BusinessConfiguration: a business (tenant)."""

    __tablename__ = 'configuration_app_businessconfiguration'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default='')
    location: Mapped[str] = mapped_column(String(255))


class BusinessUser(Base):
    """auth_app.BusinessUser (Django's AbstractUser): only what checking a login needs."""

    __tablename__ = 'auth_app_businessuser'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    username: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))


class ChatConfiguration(Base):
    """chat_app.ChatConfiguration: a business's settings for the chat flow's steps (one at most)."""

    __tablename__ = 'chat_app_chatconfiguration'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'), unique=True)
    product_detail_fields: Mapped[list] = mapped_column(Json)
    schedule_detail_fields: Mapped[list] = mapped_column(Json)
    welcome_message: Mapped[str] = mapped_column(String(1000), default='')
    reply_style: Mapped[str] = mapped_column(String(20))
    custom_style: Mapped[str] = mapped_column(String(500), default='')


class ChatSession(Base):
    """chat_app.ChatSession: a conversation between a business and one customer."""

    __tablename__ = 'chat_app_chatsession'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    phone_number: Mapped[str] = mapped_column(String(16), default='')
    display_name: Mapped[str] = mapped_column(String(150), default='')
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)
    last_chat_time: Mapped[datetime] = mapped_column(AwareDateTime)
    chat_message_json: Mapped[list] = mapped_column(Json)
    chat_state_id: Mapped[str] = mapped_column(String(32))
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_state_data: Mapped[dict] = mapped_column(Json)


class UnansweredQuestion(Base):
    """chat_app.UnansweredQuestion: a customer question the assistant couldn't answer."""

    __tablename__ = 'chat_app_unansweredquestion'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    question: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))
    faq_id: Mapped[int | None] = mapped_column(ForeignKey('product_app_faq.id'))
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)
    answered_time: Mapped[datetime | None] = mapped_column(AwareDateTime)


class InboundMessage(Base):
    """chat_app.InboundMessage: a WhatsApp message taken from Pub/Sub, one row per Meta message id
    (so a message delivered twice is answered once). Written by this service (app/inbound.py)."""

    __tablename__ = 'chat_app_inboundmessage'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    message_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # received | replied
    received_time: Mapped[datetime] = mapped_column(AwareDateTime)
    replied_time: Mapped[datetime | None] = mapped_column(AwareDateTime)


class Product(Base):
    """product_app.Product. Only total_quantity is stored: on hold / sold / available come from the
    orders (chat_flow.stock), like Django's Product.quantity_* properties."""

    __tablename__ = 'product_app_product'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default='')
    information: Mapped[str] = mapped_column(Text, default='')
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FAQ(Base):
    """product_app.FAQ."""

    __tablename__ = 'product_app_faq'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)


class ServiceProvider(Base):
    """product_app.ServiceProvider: one photographer, teacher, court…"""

    __tablename__ = 'product_app_serviceprovider'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(300), default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# product_app.Service.service_providers (Django's auto-created many-to-many table).
service_service_providers = Table(
    'product_app_service_service_providers',
    Base.metadata,
    Column('id', BigId, primary_key=True),
    Column('service_id', ForeignKey('product_app_service.id'), nullable=False),
    Column('serviceprovider_id', ForeignKey('product_app_serviceprovider.id'), nullable=False),
)


class Service(Base):
    """product_app.Service: something customers book a time for."""

    __tablename__ = 'product_app_service'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default='')
    information: Mapped[str] = mapped_column(Text, default='')
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    start_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WeeklyAvailability(Base):
    """product_app.WeeklyAvailability: a provider's week (its Monday), 672 letters (O / U / H / X)."""

    __tablename__ = 'product_app_weeklyavailability'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    service_provider_id: Mapped[int] = mapped_column(ForeignKey('product_app_serviceprovider.id'))
    week: Mapped[date] = mapped_column(Date)
    availability: Mapped[str] = mapped_column(String(672))


class OrderItem(Base):
    """checkout_app.OrderItem: an order of products (its lines in order_data)."""

    __tablename__ = 'checkout_app_orderitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    order_data: Mapped[dict] = mapped_column(Json)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32), index=True)
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)
    updated_time: Mapped[datetime] = mapped_column(AwareDateTime)

    @property
    def total(self) -> Decimal:
        """Sum of unit_price × quantity over the items (Django's OrderItem.total)."""
        items = self.order_data.get('items', []) if isinstance(self.order_data, dict) else []
        return sum((Decimal(item['unit_price']) * item['quantity'] for item in items), Decimal('0.00'))


class ScheduleItem(Base):
    """checkout_app.ScheduleItem: a booking of a service provider's time."""

    __tablename__ = 'checkout_app_scheduleitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('configuration_app_businessconfiguration.id'))
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey('chat_app_chatsession.id'))
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    service_id: Mapped[int | None] = mapped_column(ForeignKey('product_app_service.id'))
    service_provider_id: Mapped[int | None] = mapped_column(ForeignKey('product_app_serviceprovider.id'))
    start_time: Mapped[datetime] = mapped_column(AwareDateTime)
    end_time: Mapped[datetime] = mapped_column(AwareDateTime)
    blocked_until: Mapped[datetime] = mapped_column(AwareDateTime)
    schedule_data: Mapped[dict] = mapped_column(Json)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32), index=True)
    created_time: Mapped[datetime] = mapped_column(AwareDateTime)
    updated_time: Mapped[datetime] = mapped_column(AwareDateTime)

    @property
    def total(self) -> Decimal:
        """The service's price (from the snapshot; Django's ScheduleItem.total)."""
        service = self.schedule_data.get('service', {}) if isinstance(self.schedule_data, dict) else {}
        return Decimal(service.get('price', '0.00'))
