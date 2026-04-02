from __future__ import annotations

from collections import OrderedDict
from typing import Any

from django_cb.exceptions import (
    DocumentDoesNotExist,
    MultipleDocumentsReturned,
    OperationError,
    ValidationError,
)
from django_cb.fields.base import BaseField
from django_cb.options import DocumentOptions
from django_cb.utils import generate_id

# Global registry of all Document subclasses, keyed by class name
_document_registry: dict[str, type] = {}


def get_document_registry() -> dict[str, type]:
    return _document_registry


class DocumentMetaclass(type):
    """Metaclass for Document classes.

    Collects field definitions, builds DocumentOptions, attaches the manager,
    and registers the document class.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> DocumentMetaclass:
        # Collect fields from current class
        fields = OrderedDict()
        for attr_name, attr_value in list(namespace.items()):
            if isinstance(attr_value, BaseField):
                attr_value.name = attr_name
                fields[attr_name] = attr_value

        # Collect inherited fields from base classes
        for base in reversed(bases):
            if hasattr(base, "_meta") and hasattr(base._meta, "fields"):
                for field_name, field in base._meta.fields.items():
                    if field_name not in fields:
                        fields[field_name] = field

        # Sort by creation order
        fields = OrderedDict(sorted(fields.items(), key=lambda item: item[1]._creation_order))

        # Build DocumentOptions from inner Meta class
        meta_class = namespace.pop("Meta", None)
        options = DocumentOptions(meta_class)
        options.fields = fields

        # Set collection_name default from class name
        if not options.collection_name and not options.abstract:
            options.collection_name = name.lower()

        # Set doc_type_value from class name
        options.doc_type_value = name.lower()

        namespace["_meta"] = options

        # Remove field instances from namespace (they're tracked in _meta.fields)
        # but keep them accessible via descriptors on the class
        cls = super().__new__(mcs, name, bases, namespace)

        # Remove field instances from the class dict so they don't shadow
        # __getattr__/__setattr__ data access on instances
        for field_name in fields:
            if field_name in cls.__dict__:
                delattr(cls, field_name)

        # Create per-class DoesNotExist and MultipleObjectsReturned exceptions
        if name != "Document":
            cls.DoesNotExist = type(
                "DoesNotExist", (DocumentDoesNotExist,), {"__module__": namespace.get("__module__", "")}
            )
            cls.MultipleObjectsReturned = type(
                "MultipleObjectsReturned",
                (MultipleDocumentsReturned,),
                {"__module__": namespace.get("__module__", "")},
            )

        # Attach the manager
        if not options.abstract and name != "Document":
            from django_cb.queryset.manager import DocumentManager

            if "objects" not in namespace:
                cls.objects = DocumentManager()
            cls.objects.contribute_to_class(cls)

        # Register the class
        if name != "Document" and not options.abstract:
            _document_registry[name] = cls

        return cls


class Document(metaclass=DocumentMetaclass):
    """Base class for all Couchbase documents.

    Provides CRUD operations, field validation, and serialization.
    """

    class Meta:
        abstract = True

    def __init__(self, _id: str | None = None, **kwargs):
        self._id: str = _id or generate_id()
        self._data: dict[str, Any] = {}
        self._is_new: bool = True
        self._cas: int | None = None

        # Set field values from kwargs or defaults
        for field_name, field in self._meta.fields.items():
            if field_name in kwargs:
                value = kwargs[field_name]
            elif field.has_default():
                value = field.get_default()
            else:
                value = None
            self._data[field_name] = value

        # Check for unexpected kwargs
        unexpected = set(kwargs.keys()) - set(self._meta.fields.keys())
        if unexpected:
            raise TypeError(f"Unexpected keyword arguments: {', '.join(unexpected)}")

    @property
    def pk(self) -> str:
        """The primary key (document ID) for this document."""
        return self._id

    @pk.setter
    def pk(self, value: str) -> None:
        self._id = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == "pk":
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        # Check if it's a class-level descriptor (like the manager)
        for cls in type(self).__mro__:
            if name in cls.__dict__:
                attr = cls.__dict__[name]
                if hasattr(attr, "__get__"):
                    return attr.__get__(self, type(self))
                return attr
        if name in self._meta.fields:
            return self._data.get(name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name == "pk":
            super().__setattr__(name, value)
        elif hasattr(self, "_meta") and name in self._meta.fields:
            self._data[name] = value
        else:
            super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.pk}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Document):
            return NotImplemented
        return type(self) is type(other) and self.pk == other.pk

    def __hash__(self) -> int:
        return hash((type(self), self.pk))

    @property
    def subdoc(self):
        """Access sub-document operations for this document."""
        from django_cb.query.subdoc import SubDocAccessor

        return SubDocAccessor(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the document to a JSON-compatible dict for Couchbase storage."""
        data = {}
        for field_name, field in self._meta.fields.items():
            value = self._data.get(field_name)
            if value is not None:
                data[field.get_db_field()] = field.to_json(value)
            elif field.required:
                data[field.get_db_field()] = None
        # Add type discriminator
        data[self._meta.doc_type_field] = self._meta.doc_type_value
        return data

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> Document:
        """Create a Document instance from a Couchbase document key and dict.

        This is used to hydrate documents fetched from Couchbase.
        """
        kwargs = {}
        for field_name, field in cls._meta.fields.items():
            db_field = field.get_db_field()
            if db_field in data:
                kwargs[field_name] = field.to_python(data[db_field])
        instance = cls(_id=key, **kwargs)
        instance._is_new = False
        return instance

    def full_clean(self) -> None:
        """Validate all fields on the document. Raises ValidationError."""
        errors = {}
        for field_name, field in self._meta.fields.items():
            value = self._data.get(field_name)
            try:
                field.validate(value)
            except ValidationError as e:
                errors[field_name] = e.message
        if errors:
            raise ValidationError(errors=errors)
        self.clean()

    def clean(self) -> None:
        """Hook for custom document-level validation. Override in subclasses."""

    def _get_collection(self):
        """Get the Couchbase Collection for this document class."""
        from django_cb.connection import get_collection

        return get_collection(
            alias=self._meta.bucket_alias,
            scope=self._meta.scope_name,
            collection=self._meta.collection_name,
        )

    def save(self, validate: bool = True) -> None:
        """Save the document to Couchbase.

        Uses upsert to create or replace the document.
        Fires pre_save and post_save signals.
        """
        from django_cb.signals import post_save, pre_save

        created = self._is_new

        # Apply pre_save_value for fields that support it (auto_now, auto_now_add)
        for field_name, field in self._meta.fields.items():
            if hasattr(field, "pre_save_value"):
                self._data[field_name] = field.pre_save_value(self._data.get(field_name), self._is_new)

        if validate:
            self.full_clean()

        pre_save.send(sender=type(self), instance=self, created=created)

        collection = self._get_collection()
        data = self.to_dict()

        try:
            from couchbase.options import UpsertOptions

            result = collection.upsert(self.pk, data, UpsertOptions())
            self._cas = result.cas
            self._is_new = False
        except Exception as e:
            raise OperationError(f"Failed to save document '{self.pk}': {e}") from e

        post_save.send(sender=type(self), instance=self, created=created)

    def delete(self) -> None:
        """Delete the document from Couchbase.

        Fires pre_delete and post_delete signals.
        """
        from django_cb.signals import post_delete, pre_delete

        pre_delete.send(sender=type(self), instance=self)

        collection = self._get_collection()
        try:
            collection.remove(self.pk)
        except Exception as e:
            raise OperationError(f"Failed to delete document '{self.pk}': {e}") from e

        post_delete.send(sender=type(self), instance=self)

    def reload(self) -> None:
        """Re-fetch the document from Couchbase and update local data."""
        collection = self._get_collection()
        try:
            result = collection.get(self.pk)
            data = result.content_as[dict]
            for field_name, field in self._meta.fields.items():
                db_field = field.get_db_field()
                if db_field in data:
                    self._data[field_name] = field.to_python(data[db_field])
            self._cas = result.cas
            self._is_new = False
        except Exception as e:
            raise OperationError(f"Failed to reload document '{self.pk}': {e}") from e
