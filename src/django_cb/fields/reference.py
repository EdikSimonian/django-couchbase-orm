"""ReferenceField for cross-document references with lazy loading."""

from __future__ import annotations

from typing import Any

from django_cb.exceptions import ValidationError
from django_cb.fields.base import BaseField


class ReferenceField(BaseField):
    """A field that stores a reference to another Document.

    Stores the document key as a string in Couchbase.
    On access, lazily loads the referenced document.

    Usage:
        class Beer(Document):
            name = StringField()
            brewery = ReferenceField('Brewery')
            # or: brewery = ReferenceField(Brewery)

        beer = Beer.objects.get(pk='my-beer')
        beer.brewery  # returns the key string (stored value)
        beer.get_brewery()  # loads and returns the Brewery document
    """

    def __init__(self, document_type: type | str, **kwargs):
        self.document_type = document_type
        self._resolved_type: type | None = None
        super().__init__(**kwargs)

    def _resolve_type(self) -> type:
        """Resolve string document type references to actual classes."""
        if self._resolved_type is not None:
            return self._resolved_type

        if isinstance(self.document_type, type):
            self._resolved_type = self.document_type
            return self._resolved_type

        # Resolve string reference from the document registry
        from django_cb.document import get_document_registry

        registry = get_document_registry()
        if self.document_type in registry:
            self._resolved_type = registry[self.document_type]
            return self._resolved_type

        raise ValidationError(f"Field '{self.name}': Could not resolve document type '{self.document_type}'.")

    def to_python(self, value: Any) -> str | None:
        """Returns the stored key string. Use dereference() to load the document."""
        if value is None:
            return None
        return str(value)

    def to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        # Accept either a string key or a Document instance
        if hasattr(value, "pk"):
            return str(value.pk)
        return str(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        # Accept string keys or Document instances
        if hasattr(value, "pk"):
            return
        if not isinstance(value, str):
            raise ValidationError(f"Field '{self.name}' expected a string key or Document, got {type(value).__name__}.")

    def dereference(self, key: str):
        """Load the referenced document by key.

        Returns the Document instance or raises DoesNotExist.
        """
        doc_class = self._resolve_type()
        return doc_class.objects.get(pk=key)
