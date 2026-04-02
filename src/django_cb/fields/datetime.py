"""DateTime and Date fields with auto_now / auto_now_add support."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from django_cb.exceptions import ValidationError
from django_cb.fields.base import BaseField


class DateTimeField(BaseField):
    """A field that stores datetime values as ISO 8601 strings in Couchbase."""

    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs):
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError) as e:
                raise ValidationError(f"Field '{self.name}' could not parse datetime from '{value}'.") from e
        raise ValidationError(f"Field '{self.name}' expected a datetime or ISO string, got {type(value).__name__}.")

    def to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            # Validate it parses
            datetime.fromisoformat(value)
            return value
        raise ValidationError(f"Field '{self.name}' cannot serialize {type(value).__name__} to JSON.")

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, (datetime, str)):
            raise ValidationError(f"Field '{self.name}' expected a datetime or ISO string, got {type(value).__name__}.")
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Field '{self.name}' value '{value}' is not a valid ISO 8601 datetime.")

    def pre_save_value(self, value: Any, is_new: bool) -> Any:
        """Called by Document.save() to handle auto_now / auto_now_add."""
        now = datetime.now(timezone.utc)
        if self.auto_now:
            return now
        if self.auto_now_add and is_new:
            return now
        return value


class DateField(BaseField):
    """A field that stores date values as ISO 8601 strings (YYYY-MM-DD)."""

    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs):
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except (ValueError, TypeError) as e:
                raise ValidationError(f"Field '{self.name}' could not parse date from '{value}'.") from e
        raise ValidationError(f"Field '{self.name}' expected a date or ISO string, got {type(value).__name__}.")

    def to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            date.fromisoformat(value)
            return value
        raise ValidationError(f"Field '{self.name}' cannot serialize {type(value).__name__} to JSON.")

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, (date, str)):
            raise ValidationError(f"Field '{self.name}' expected a date or ISO string, got {type(value).__name__}.")
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Field '{self.name}' value '{value}' is not a valid ISO 8601 date.")

    def pre_save_value(self, value: Any, is_new: bool) -> Any:
        """Called by Document.save() to handle auto_now / auto_now_add."""
        today = date.today()
        if self.auto_now:
            return today
        if self.auto_now_add and is_new:
            return today
        return value
