"""Sub-document operations for partial reads and writes on Couchbase documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_couchbase_orm.exceptions import OperationError

if TYPE_CHECKING:
    from django_couchbase_orm.document import Document


class SubDocAccessor:
    """Provides sub-document operations on a Document instance.

    Access via `document.subdoc`:
        user.subdoc.get("address.city")
        user.subdoc.upsert("address.city", "New York")
        user.subdoc.remove("address.temp_field")
        user.subdoc.array_append("tags", "vip")
        user.subdoc.increment("login_count", 1)
    """

    def __init__(self, document: Document):
        self._document = document

    @property
    def _collection(self):
        return self._document._get_collection()

    def get(self, path: str) -> Any:
        """Get a value at the given sub-document path."""
        try:
            import couchbase.subdocument as SD

            result = self._collection.lookup_in(self._document.pk, [SD.get(path)])
            # Use the raw value from the result to preserve type (int, str, dict, etc.)
            return result.value[0]["value"]
        except Exception as e:
            raise OperationError(f"Sub-document get failed for path '{path}': {e}") from e

    def exists(self, path: str) -> bool:
        """Check if a path exists in the document."""
        try:
            import couchbase.subdocument as SD

            result = self._collection.lookup_in(self._document.pk, [SD.exists(path)])
            return result.exists(0)
        except Exception as e:
            raise OperationError(f"Sub-document exists failed for path '{path}': {e}") from e

    def count(self, path: str) -> int:
        """Count elements at the given path (array length or dict key count)."""
        try:
            import couchbase.subdocument as SD

            result = self._collection.lookup_in(self._document.pk, [SD.count(path)])
            return result.value[0]["value"]
        except Exception as e:
            raise OperationError(f"Sub-document count failed for path '{path}': {e}") from e

    def upsert(self, path: str, value: Any, create_parents: bool = True) -> None:
        """Insert or update a value at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.upsert(path, value, create_parents=create_parents)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document upsert failed for path '{path}': {e}") from e

    def insert(self, path: str, value: Any, create_parents: bool = False) -> None:
        """Insert a value at the given path. Fails if the path already exists."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.insert(path, value, create_parents=create_parents)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document insert failed for path '{path}': {e}") from e

    def replace(self, path: str, value: Any) -> None:
        """Replace a value at the given path. Fails if the path doesn't exist."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.replace(path, value)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document replace failed for path '{path}': {e}") from e

    def remove(self, path: str) -> None:
        """Remove a value at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.remove(path)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document remove failed for path '{path}': {e}") from e

    def array_append(self, path: str, *values: Any, create_parents: bool = True) -> None:
        """Append values to an array at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.array_append(path, *values, create_parents=create_parents)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document array_append failed for path '{path}': {e}") from e

    def array_prepend(self, path: str, *values: Any, create_parents: bool = True) -> None:
        """Prepend values to an array at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.array_prepend(path, *values, create_parents=create_parents)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document array_prepend failed for path '{path}': {e}") from e

    def array_addunique(self, path: str, value: Any, create_parents: bool = True) -> None:
        """Add a value to an array only if it doesn't already exist (set semantics)."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.array_addunique(path, value, create_parents=create_parents)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document array_addunique failed for path '{path}': {e}") from e

    def increment(self, path: str, delta: int = 1) -> None:
        """Increment a numeric value at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.increment(path, delta)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document increment failed for path '{path}': {e}") from e

    def decrement(self, path: str, delta: int = 1) -> None:
        """Decrement a numeric value at the given path."""
        try:
            import couchbase.subdocument as SD

            self._collection.mutate_in(
                self._document.pk,
                [SD.decrement(path, delta)],
            )
        except Exception as e:
            raise OperationError(f"Sub-document decrement failed for path '{path}': {e}") from e

    def multi_lookup(self, *specs) -> list:
        """Perform multiple lookup operations in a single call.

        Args:
            specs: couchbase.subdocument spec objects (SD.get, SD.exists, SD.count)

        Returns:
            The LookupInResult object.
        """
        try:
            return self._collection.lookup_in(self._document.pk, list(specs))
        except Exception as e:
            raise OperationError(f"Sub-document multi_lookup failed: {e}") from e

    def multi_mutate(self, *specs) -> None:
        """Perform multiple mutation operations in a single call.

        Args:
            specs: couchbase.subdocument spec objects (SD.upsert, SD.insert, etc.)
        """
        try:
            self._collection.mutate_in(self._document.pk, list(specs))
        except Exception as e:
            raise OperationError(f"Sub-document multi_mutate failed: {e}") from e
