"""Small stand-ins for django.utils.timezone / dateparse."""

from datetime import UTC, datetime


def now() -> datetime:
    """django.utils.timezone.now() with USE_TZ: the current time, aware, in UTC."""
    return datetime.now(UTC)


def parse_datetime(value: str) -> datetime | None:
    """django.utils.dateparse.parse_datetime: an ISO 8601 date-time, or None if it isn't one."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_aware(value: datetime) -> bool:
    return value.utcoffset() is not None
