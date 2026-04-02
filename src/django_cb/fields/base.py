from __future__ import annotations

import copy
from typing import Any

from django_cb.exceptions import ValidationError


class BaseField:
    """Base class for all document fields.

    Handles common functionality: defaults, required validation,
    choices, custom validators, and serialization hooks.
    """

    _creation_counter = 0

    def __init__(
        self,
        required: bool = False,
        default: Any = None,
        choices: list | tuple | None = None,
        db_field: str | None = None,
        validators: list | None = None,
        help_text: str = "",
    ):
        self.required = required
        self.default = default
        self.choices = choices
        self.db_field = db_field
        self.validators = validators or []
        self.help_text = help_text

        # Set by DocumentMetaclass
        self.name: str = ""

        # Preserve declaration order
        self._creation_order = BaseField._creation_counter
        BaseField._creation_counter += 1

    def get_db_field(self) -> str:
        """Return the JSON key name used when storing this field in Couchbase."""
        return self.db_field or self.name

    def get_default(self) -> Any:
        """Return the default value, calling it if it's a callable."""
        if callable(self.default):
            return self.default()
        return copy.deepcopy(self.default)

    def has_default(self) -> bool:
        return self.default is not None

    def to_python(self, value: Any) -> Any:
        """Convert a value from Couchbase JSON to a Python object.

        Subclasses should override this for type coercion.
        """
        return value

    def to_json(self, value: Any) -> Any:
        """Convert a Python value to a JSON-serializable value for Couchbase.

        Subclasses should override this for type serialization.
        """
        return value

    def validate(self, value: Any) -> None:
        """Validate a field value. Raises ValidationError on failure."""
        if value is None:
            if self.required:
                raise ValidationError(f"Field '{self.name}' is required.")
            return

        if self.choices is not None:
            choice_values = [c[0] if isinstance(c, (list, tuple)) else c for c in self.choices]
            if value not in choice_values:
                raise ValidationError(
                    f"Value '{value}' is not a valid choice for field '{self.name}'. Valid choices: {choice_values}"
                )

        for validator in self.validators:
            validator(value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
