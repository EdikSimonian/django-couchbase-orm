"""Compound fields for nested data structures: lists, dicts, and embedded documents."""

from __future__ import annotations

from typing import Any

from django_cb.exceptions import ValidationError
from django_cb.fields.base import BaseField


class ListField(BaseField):
    """A field that stores a list of values.

    Optionally takes a `field` argument to validate/coerce each element.
    """

    def __init__(
        self, field: BaseField | None = None, min_length: int | None = None, max_length: int | None = None, **kwargs
    ):
        self.field = field
        self.min_length = min_length
        self.max_length = max_length
        if self.field:
            self.field.name = "list_item"
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> list | None:
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"Field '{self.name}' expected a list, got {type(value).__name__}.")
        if self.field:
            return [self.field.to_python(item) for item in value]
        return list(value)

    def to_json(self, value: Any) -> list | None:
        if value is None:
            return None
        if self.field:
            return [self.field.to_json(item) for item in value]
        return list(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"Field '{self.name}' expected a list, got {type(value).__name__}.")
        if self.min_length is not None and len(value) < self.min_length:
            raise ValidationError(f"Field '{self.name}' list is too short. Minimum length is {self.min_length}.")
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(f"Field '{self.name}' list is too long. Maximum length is {self.max_length}.")
        if self.field:
            for i, item in enumerate(value):
                try:
                    self.field.validate(item)
                except ValidationError as e:
                    raise ValidationError(f"Field '{self.name}' item at index {i}: {e.message}") from e


class DictField(BaseField):
    """A field that stores a dictionary (JSON object)."""

    def to_python(self, value: Any) -> dict | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValidationError(f"Field '{self.name}' expected a dict, got {type(value).__name__}.")
        return dict(value)

    def to_json(self, value: Any) -> dict | None:
        if value is None:
            return None
        return dict(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if not isinstance(value, dict):
            raise ValidationError(f"Field '{self.name}' expected a dict, got {type(value).__name__}.")


class EmbeddedDocument:
    """Base class for embedded (nested) documents.

    Unlike Document, these are not stored independently — they exist
    as nested objects within a parent Document.
    """

    def __init__(self, **kwargs):
        self._data = {}
        for key, value in kwargs.items():
            if key in self._fields:
                self._data[key] = value
            else:
                raise TypeError(f"Unexpected field: {key}")

        # Set defaults for unset fields
        for name, field in self._fields.items():
            if name not in self._data:
                if field.has_default():
                    self._data[name] = field.get_default()
                else:
                    self._data[name] = None

    @classmethod
    def _get_fields(cls) -> dict[str, BaseField]:
        """Collect all BaseField instances from the class."""
        fields = {}
        for klass in reversed(cls.__mro__):
            for attr_name, attr_value in klass.__dict__.items():
                if isinstance(attr_value, BaseField):
                    attr_value.name = attr_name
                    fields[attr_name] = attr_value
        return fields

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._fields = cls._get_fields()
        # Remove field instances from class dict so they don't shadow __getattr__
        for field_name in cls._fields:
            if field_name in cls.__dict__:
                delattr(cls, field_name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        if name in self._fields:
            return self._data.get(name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        elif hasattr(self, "_fields") and name in self._fields:
            self._data[name] = value
        else:
            super().__setattr__(name, value)

    def __eq__(self, other):
        if not isinstance(other, EmbeddedDocument):
            return NotImplemented
        return type(self) is type(other) and self._data == other._data

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self._data}>"

    def to_dict(self) -> dict:
        data = {}
        for name, field in self._fields.items():
            value = self._data.get(name)
            if value is not None:
                if isinstance(value, EmbeddedDocument):
                    data[field.get_db_field()] = value.to_dict()
                else:
                    data[field.get_db_field()] = field.to_json(value)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> EmbeddedDocument:
        kwargs = {}
        for name, field in cls._fields.items():
            db_field = field.get_db_field()
            if db_field in data:
                if isinstance(field, EmbeddedDocumentField):
                    kwargs[name] = field.document_class.from_dict(data[db_field])
                else:
                    kwargs[name] = field.to_python(data[db_field])
        return cls(**kwargs)

    def validate(self) -> None:
        errors = {}
        for name, field in self._fields.items():
            value = self._data.get(name)
            try:
                field.validate(value)
            except ValidationError as e:
                errors[name] = e.message
        if errors:
            raise ValidationError(errors=errors)


class EmbeddedDocumentField(BaseField):
    """A field that stores a nested EmbeddedDocument."""

    def __init__(self, document_class: type[EmbeddedDocument], **kwargs):
        self.document_class = document_class
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> EmbeddedDocument | None:
        if value is None:
            return None
        if isinstance(value, self.document_class):
            return value
        if isinstance(value, dict):
            return self.document_class.from_dict(value)
        raise ValidationError(
            f"Field '{self.name}' expected a {self.document_class.__name__} or dict, got {type(value).__name__}."
        )

    def to_json(self, value: Any) -> dict | None:
        if value is None:
            return None
        if isinstance(value, EmbeddedDocument):
            return value.to_dict()
        if isinstance(value, dict):
            return value
        raise ValidationError(f"Field '{self.name}' cannot serialize {type(value).__name__} to JSON.")

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if isinstance(value, dict):
            value = self.document_class.from_dict(value)
        if not isinstance(value, self.document_class):
            raise ValidationError(
                f"Field '{self.name}' expected a {self.document_class.__name__}, got {type(value).__name__}."
            )
        value.validate()
