"""SQLAlchemy models of the configuration-service (Django) tables the payment flow reads and writes.

configuration-service owns the schema and its migrations: never create or alter tables from here
(the tests' create_all on SQLite is the only exception). Only the columns the flow needs are mapped;
keep them in sync with the Django models (checkout_app.OrderItem / ScheduleItem,
product_app.WeeklyAvailability). Django's table name is <app_label>_<model name>.
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String
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


class OrderItem(Base):
    """checkout_app.OrderItem: an order of products. Its quantities aren't stored on the products:
    configuration-service derives on hold / sold / available from the orders' statuses."""

    __tablename__ = 'checkout_app_orderitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger)
    order_status: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(32), index=True)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduleItem(Base):
    """checkout_app.ScheduleItem: a booking of a service provider's time."""

    __tablename__ = 'checkout_app_scheduleitem'

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    business_id: Mapped[int] = mapped_column(BigInteger)
    service_provider_id: Mapped[int | None] = mapped_column(BigInteger)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
