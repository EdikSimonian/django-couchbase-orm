from __future__ import annotations

import uuid
from typing import Any

from django_couchbase_orm.exceptions import ValidationError
from django_couchbase_orm.fields.base import BaseField


class StringField(BaseField):
    """A field that stores string values."""

    def __init__(
        self,
        min_length: int | None = None,
        max_length: int | None = None,
        regex: str | None = None,
        **kwargs,
    ):
        self.min_length = min_length
        self.max_length = max_length
        self.regex = regex
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return

        if not isinstance(value, str):
            raise ValidationError(f"Field '{self.name}' expected a string, got {type(value).__name__}.")

        if self.min_length is not None and len(value) < self.min_length:
            raise ValidationError(f"Field '{self.name}' value is too short. Minimum length is {self.min_length}.")

        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(f"Field '{self.name}' value is too long. Maximum length is {self.max_length}.")

        if self.regex is not None:
            import re

            if not re.match(self.regex, value):
                raise ValidationError(f"Field '{self.name}' value does not match pattern '{self.regex}'.")


class IntegerField(BaseField):
    """A field that stores integer values."""

    def __init__(
        self,
        min_value: int | None = None,
        max_value: int | None = None,
        **kwargs,
    ):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Field '{self.name}' could not convert {value!r} to int.") from e

    def to_json(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return

        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"Field '{self.name}' expected an integer, got {type(value).__name__}.")

        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"Field '{self.name}' value {value} is less than minimum {self.min_value}.")

        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"Field '{self.name}' value {value} is greater than maximum {self.max_value}.")


class FloatField(BaseField):
    """A field that stores float values."""

    def __init__(
        self,
        min_value: float | None = None,
        max_value: float | None = None,
        **kwargs,
    ):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Field '{self.name}' could not convert {value!r} to float.") from e

    def to_json(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"Field '{self.name}' expected a number, got {type(value).__name__}.")

        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"Field '{self.name}' value {value} is less than minimum {self.min_value}.")

        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"Field '{self.name}' value {value} is greater than maximum {self.max_value}.")


class BooleanField(BaseField):
    """A field that stores boolean values."""

    _TRUE_STRINGS = frozenset({"true", "t", "yes", "y", "1"})
    _FALSE_STRINGS = frozenset({"false", "f", "no", "n", "0", ""})

    @classmethod
    def _coerce(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            # Reject only NaN; otherwise honor 0/non-zero semantics.
            if isinstance(value, float) and value != value:  # NaN
                raise ValidationError("BooleanField cannot accept NaN.")
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in cls._TRUE_STRINGS:
                return True
            if normalized in cls._FALSE_STRINGS:
                return False
            raise ValidationError(f"BooleanField cannot interpret string {value!r} as a boolean.")
        raise ValidationError(f"BooleanField expected bool/int/str, got {type(value).__name__}.")

    def to_python(self, value: Any) -> bool | None:
        return self._coerce(value)

    def to_json(self, value: Any) -> bool | None:
        return self._coerce(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return

        if not isinstance(value, bool):
            raise ValidationError(f"Field '{self.name}' expected a boolean, got {type(value).__name__}.")


class UUIDField(BaseField):
    """A field that stores UUID values. Serialized as a string in Couchbase."""

    def __init__(self, auto: bool = False, **kwargs):
        self.auto = auto
        if auto and "default" not in kwargs:
            kwargs["default"] = uuid.uuid4
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError) as e:
            raise ValidationError(f"Field '{self.name}' could not convert {value!r} to UUID.") from e

    def to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return

        if not isinstance(value, uuid.UUID):
            try:
                uuid.UUID(str(value))
            except (ValueError, AttributeError):
                raise ValidationError(f"Field '{self.name}' is not a valid UUID: {value!r}.")
