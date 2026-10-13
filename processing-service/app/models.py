"""
SQLAlchemy models of the configuration-service (Django) tables the payment flow reads and writes.

configuration-service owns the schema and its migrations: never create or alter tables from here
(the tests' create_all on SQLite is the only exception). Only the columns the flow needs are mapped;
keep them in sync with the Django models (checkout_app.OrderItem / ScheduleItem,
product_app.WeeklyAvailability). Django's table name is <app_label>_<model name>.
"""

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# checkout_app.models.OrderStatus
PENDING_PAYMENT = 'pending_payment'
PAYMENT_RECEIVED = 'payment_received'
ORDER_COMPLETED = 'order_completed'
PAYMENT_FAILED = 'payment_failed'

# product_app.models: one letter per 15-minute block of a provider's week.
SLOT_MINUTES = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96
SLOT_AVAILABLE = 'O'
SLOT_UNAVAILABLE = 'U'
SLOT_ON_HOLD = 'H'  # booked, payment pending
SLOT_BOOKED = 'X'  # booked and paid (or done)
BOOKED_LETTERS = (SLOT_ON_HOLD, SLOT_BOOKED)
UNAVAILABLE_WEEK = SLOT_UNAVAILABLE * SLOTS_PER_DAY * 7


# Django's BigAutoField. SQLite (tests) only auto-increments INTEGER primary keys.
BigId = BigInteger().with_variant(Integer, 'sqlite')


class Base(DeclarativeBase):
    pass


class BusinessConfiguration(Base):
    """configuration_app.BusinessConfiguration: a business. Only its name and location are read for the invoice."""

    __tablename__ = 'configuration_app_businessconfiguration'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(150))
    location: Mapped[str] = mapped_column(String(255))


class ChatSession(Base):
    """chat_app.ChatSession: a customer's chat. Only who the customer is is read for the invoice."""

    __tablename__ = 'chat_app_chatsession'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(16))  # '' for a sandbox chat
    display_name: Mapped[str] = mapped_column(String(150))


class ServiceProvider(Base):
    """product_app.ServiceProvider: who a service is booked with. Only its name is read for the invoice."""

    __tablename__ = 'product_app_serviceprovider'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))


class OrderItem(Base):
    """checkout_app.OrderItem: an order of products. Its quantities aren't stored on the products:
    configuration-service derives on hold / sold / available from the orders' statuses."""

    __tablename__ = 'checkout_app_orderitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger)
    chat_session_id: Mapped[int | None] = mapped_column(BigInteger)
    is_sandbox: Mapped[bool] = mapped_column(Boolean)
    order_data: Mapped[dict] = mapped_column(JSON)  # {items: [{name, unit_price, quantity, ...}], details: {...}}
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32), index=True)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduleItem(Base):
    """checkout_app.ScheduleItem: a booking of a service provider's time."""

    __tablename__ = 'checkout_app_scheduleitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger)
    chat_session_id: Mapped[int | None] = mapped_column(BigInteger)
    is_sandbox: Mapped[bool] = mapped_column(Boolean)
    service_provider_id: Mapped[int | None] = mapped_column(BigInteger)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schedule_data: Mapped[dict] = mapped_column(JSON)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32), index=True)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WeeklyAvailability(Base):
    """product_app.WeeklyAvailability: a provider's week (its Monday), 672 letters (O / U / H / X)."""

    __tablename__ = 'product_app_weeklyavailability'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    service_provider_id: Mapped[int] = mapped_column(BigInteger)
    week: Mapped[date] = mapped_column(Date)
    availability: Mapped[str] = mapped_column(String(SLOTS_PER_DAY * 7), default=UNAVAILABLE_WEEK)
