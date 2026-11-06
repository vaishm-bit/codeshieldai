"""Custom SQLAlchemy column types."""

from enum import Enum as PyEnum

from datetime import timezone

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """SQLite has no timezone support: store naive UTC, return aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def enum_type(enum_cls: type[PyEnum], length: int = 32) -> Enum:
    """Store a Python enum by its value (e.g. 'Critical'), as a validated string."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
