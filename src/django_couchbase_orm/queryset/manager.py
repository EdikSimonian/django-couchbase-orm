from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_couchbase_orm.exceptions import DocumentDoesNotExist, OperationError

if TYPE_CHECKING:
    from django_couchbase_orm.document import Document
    from django_couchbase_orm.queryset.queryset import QuerySet


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
        from django_couchbase_orm.connection import get_collection

        cls = self._document_class
        return get_collection(
            alias=cls._meta.bucket_alias,
            scope=cls._meta.scope_name,
            collection=cls._meta.collection_name,
        )

    def _get_queryset(self) -> QuerySet:
        """Create a new QuerySet for this manager's document class."""
        from django_couchbase_orm.queryset.queryset import QuerySet

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

    def select_related(self, *fields) -> QuerySet:
        return self._get_queryset().select_related(*fields)

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
    # Async QuerySet delegation
    # ============================================================

    async def acount(self) -> int:
        return await self._get_queryset().acount()

    async def afirst(self):
        return await self._get_queryset().afirst()

    async def alist(self) -> list:
        return await self._get_queryset().alist()

    async def aget(self, pk: str | None = None, *args, **kwargs):
        """Async get — KV fast path for pk, N1QL for field lookups."""
        if pk is not None:
            return await self._aget_by_pk(pk)
        if args or kwargs:
            return await self._get_queryset().aget(*args, **kwargs)
        raise ValueError("aget() requires at least one lookup argument.")

    async def _aget_by_pk(self, pk: str):
        """Async fetch by primary key using KV."""
        try:
            from couchbase.exceptions import DocumentNotFoundException

            from django_couchbase_orm.async_connection import get_async_collection

            collection = await get_async_collection(
                alias=self._document_class._meta.bucket_alias,
                scope=self._document_class._meta.scope_name,
                collection=self._document_class._meta.collection_name,
            )
            result = await collection.get(pk)
            data = result.content_as[dict]

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

    async def acreate(self, _id: str | None = None, **kwargs):
        """Async version of create()."""
        instance = self._document_class(_id=_id, **kwargs)
        instance.full_clean()
        await instance.asave(validate=False)
        return instance

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

    def bulk_create(self, documents: list[Document]) -> list[Document]:
        """Create multiple documents in batch.

        Validates all documents first, then upserts them.
        Returns the list of saved documents.
        """
        for doc in documents:
            doc.full_clean()

        collection = self._collection
        try:
            from couchbase.options import UpsertOptions

            for doc in documents:
                data = doc.to_dict()
                result = collection.upsert(doc.pk, data, UpsertOptions())
                doc._cas = result.cas
                doc._is_new = False
        except Exception as e:
            raise OperationError(f"Failed during bulk_create: {e}") from e

        return documents

    def bulk_update(self, documents: list[Document], fields: list[str]) -> int:
        """Update specific fields on multiple documents in batch.

        Args:
            documents: List of Document instances to update.
            fields: List of field names to update.

        Returns:
            The number of documents updated.
        """
        if not documents or not fields:
            return 0

        collection = self._collection
        updated = 0
        try:
            import couchbase.subdocument as SD

            field_map = {name: field.get_db_field() for name, field in self._document_class._meta.fields.items()}

            for doc in documents:
                specs = []
                for field_name in fields:
                    if field_name not in self._document_class._meta.fields:
                        raise ValueError(f"Unknown field: {field_name}")
                    field_obj = self._document_class._meta.fields[field_name]
                    db_field = field_map.get(field_name, field_name)
                    value = doc._data.get(field_name)
                    json_value = field_obj.to_json(value) if value is not None else None
                    specs.append(SD.upsert(db_field, json_value))

                if specs:
                    collection.mutate_in(doc.pk, specs)
                    updated += 1
        except Exception as e:
            raise OperationError(f"Failed during bulk_update: {e}") from e

        return updated
