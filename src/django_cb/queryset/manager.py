from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_cb.exceptions import DocumentDoesNotExist, OperationError

if TYPE_CHECKING:
    from django_cb.document import Document
    from django_cb.queryset.queryset import QuerySet


class DocumentManager:
    """Manager for Document classes, providing document retrieval operations.

    Attached as `cls.objects` on Document subclasses.
    Delegates QuerySet-related methods (filter, exclude, order_by, etc.) to QuerySet.
    """

    def __init__(self):
        self._document_class: type[Document] | None = None

    def contribute_to_class(self, cls: type[Document]) -> None:
        """Called by DocumentMetaclass to bind this manager to a document class."""
        self._document_class = cls

    def __get__(self, instance, owner):
        """Ensure the manager is only accessible from the class, not instances."""
        if instance is not None:
            raise AttributeError("Manager is accessible via the Document class, not instances.")
        manager = self.__class__()
        manager._document_class = owner
        return manager

    @property
    def _collection(self):
        """Get the Couchbase Collection for the document class."""
        from django_cb.connection import get_collection

        cls = self._document_class
        return get_collection(
            alias=cls._meta.bucket_alias,
            scope=cls._meta.scope_name,
            collection=cls._meta.collection_name,
        )

    def _get_queryset(self) -> QuerySet:
        """Create a new QuerySet for this manager's document class."""
        from django_cb.queryset.queryset import QuerySet

        return QuerySet(self._document_class)

    # ============================================================
    # QuerySet delegation — these return a new QuerySet
    # ============================================================

    def all(self) -> QuerySet:
        return self._get_queryset()

    def filter(self, *args, **kwargs) -> QuerySet:
        return self._get_queryset().filter(*args, **kwargs)

    def exclude(self, *args, **kwargs) -> QuerySet:
        return self._get_queryset().exclude(*args, **kwargs)

    def order_by(self, *fields) -> QuerySet:
        return self._get_queryset().order_by(*fields)

    def values(self, *fields) -> QuerySet:
        return self._get_queryset().values(*fields)

    def none(self) -> QuerySet:
        return self._get_queryset().none()

    def count(self) -> int:
        return self._get_queryset().count()

    def first(self):
        return self._get_queryset().first()

    def last(self):
        return self._get_queryset().last()

    def raw(self, statement: str, params: list | None = None) -> list:
        return self._get_queryset().raw(statement, params)

    def iterator(self):
        return self._get_queryset().iterator()

    # ============================================================
    # KV-optimized operations (bypass N1QL for speed)
    # ============================================================

    def get(self, pk: str | None = None, *args, **kwargs) -> Document:
        """Retrieve a single document.

        Uses Couchbase KV get (fast path) when pk is provided.
        Falls back to N1QL QuerySet.get() for field-based lookups.
        """
        if pk is not None:
            return self._get_by_pk(pk)

        if args or kwargs:
            return self._get_queryset().get(*args, **kwargs)

        raise ValueError("get() requires at least one lookup argument.")

    def _get_by_pk(self, pk: str) -> Document:
        """Fetch a document by primary key using KV operations."""
        try:
            from couchbase.exceptions import DocumentNotFoundException

            result = self._collection.get(pk)
            data = result.content_as[dict]

            # Verify type discriminator matches
            doc_type = data.get(self._document_class._meta.doc_type_field)
            if doc_type and doc_type != self._document_class._meta.doc_type_value:
                raise self._document_class.DoesNotExist(
                    f"Document '{pk}' exists but is not of type '{self._document_class._meta.doc_type_value}'."
                )

            instance = self._document_class.from_dict(pk, data)
            instance._cas = result.cas
            return instance
        except DocumentNotFoundException:
            raise self._document_class.DoesNotExist(f"{self._document_class.__name__} with pk '{pk}' does not exist.")
        except self._document_class.DoesNotExist:
            raise
        except Exception as e:
            raise OperationError(f"Failed to get document '{pk}': {e}") from e

    def create(self, _id: str | None = None, **kwargs) -> Document:
        """Create and save a new document.

        Uses Couchbase insert to ensure the document doesn't already exist.
        """
        instance = self._document_class(_id=_id, **kwargs)
        instance.full_clean()

        try:
            from couchbase.options import InsertOptions

            data = instance.to_dict()
            result = self._collection.insert(instance.pk, data, InsertOptions())
            instance._cas = result.cas
            instance._is_new = False
            return instance
        except Exception as e:
            raise OperationError(f"Failed to create document: {e}") from e

    def get_or_create(
        self, _id: str | None = None, defaults: dict[str, Any] | None = None, **kwargs
    ) -> tuple[Document, bool]:
        """Get an existing document or create a new one.

        Returns a tuple of (document, created).
        """
        if _id is not None:
            try:
                doc = self.get(pk=_id)
                return doc, False
            except DocumentDoesNotExist:
                pass

        create_kwargs = {**kwargs, **(defaults or {})}
        doc = self.create(_id=_id, **create_kwargs)
        return doc, True

    def exists(self, pk: str) -> bool:
        """Check if a document with the given pk exists."""
        try:
            result = self._collection.exists(pk)
            return result.exists
        except Exception:
            return False
