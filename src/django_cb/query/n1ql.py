"""N1QL query builder for constructing parameterized SQL++ statements."""

from __future__ import annotations

import re
from typing import Any

_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """Validate a field/identifier name to prevent backtick injection."""
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Invalid identifier: {name!r}. Must be alphanumeric with underscores.")
    return name


class N1QLQuery:
    """Builds parameterized N1QL (SQL++) queries.

    All values are passed as positional parameters ($1, $2, ...) to prevent injection.
    """

    def __init__(self, bucket: str, scope: str = "_default", collection: str = "_default"):
        self._bucket = bucket
        self._scope = scope
        self._collection = collection
        self._select_fields: list[str] | None = None  # None = SELECT *
        self._select_raw: str | None = None  # For COUNT(*) etc.
        self._where_clauses: list[str] = []
        self._params: list[Any] = []
        self._order_by: list[str] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._use_keys: list[str] | None = None
        self._meta_id: bool = False  # Include META().id in SELECT

    @property
    def keyspace(self) -> str:
        """Fully qualified keyspace: `bucket`.`scope`.`collection`."""
        return f"`{self._bucket}`.`{self._scope}`.`{self._collection}`"

    def clone(self) -> N1QLQuery:
        """Create a deep copy of this query."""
        q = N1QLQuery(self._bucket, self._scope, self._collection)
        q._select_fields = self._select_fields[:] if self._select_fields else None
        q._select_raw = self._select_raw
        q._where_clauses = self._where_clauses[:]
        q._params = self._params[:]
        q._order_by = self._order_by[:]
        q._limit = self._limit
        q._offset = self._offset
        q._use_keys = self._use_keys[:] if self._use_keys else None
        q._meta_id = self._meta_id
        return q

    def select(self, *fields: str) -> N1QLQuery:
        """Set specific fields to select. If not called, selects all (*)."""
        self._select_fields = [_validate_identifier(f) for f in fields]
        return self

    def select_count(self) -> N1QLQuery:
        """Set query to SELECT COUNT(*)."""
        self._select_raw = "COUNT(*) AS `__count`"
        return self

    def include_meta_id(self) -> N1QLQuery:
        """Include META().id in SELECT results."""
        self._meta_id = True
        return self

    def where(self, clause: str, params: list[Any] | None = None) -> N1QLQuery:
        """Add a WHERE clause with optional parameters.

        Parameters in the clause should use the next available $N placeholder.
        Use add_param() to get the correct placeholder number.
        """
        self._where_clauses.append(clause)
        if params:
            self._params.extend(params)
        return self

    def add_param(self, value: Any) -> str:
        """Add a parameter and return its $N placeholder string."""
        self._params.append(value)
        return f"${len(self._params)}"

    def order_by(self, *fields: str) -> N1QLQuery:
        """Set ORDER BY fields. Prefix with '-' for DESC."""
        for f in fields:
            _validate_identifier(f.lstrip("-"))
        self._order_by = list(fields)
        return self

    def limit(self, n: int) -> N1QLQuery:
        self._limit = n
        return self

    def offset(self, n: int) -> N1QLQuery:
        self._offset = n
        return self

    def use_keys(self, keys: list[str]) -> N1QLQuery:
        """Optimize query with USE KEYS for direct key lookups."""
        self._use_keys = keys
        return self

    def build(self) -> tuple[str, list[Any]]:
        """Build the N1QL statement and parameter list.

        Returns:
            A tuple of (statement_string, positional_parameters).
        """
        parts = []

        # SELECT
        parts.append("SELECT")
        if self._select_raw:
            parts.append(self._select_raw)
        elif self._select_fields:
            select_parts = []
            if self._meta_id:
                select_parts.append("META(d).id AS __id")
            select_parts.extend(f"d.`{f}`" for f in self._select_fields)
            parts.append(", ".join(select_parts))
        else:
            if self._meta_id:
                parts.append("META(d).id AS __id, d.*")
            else:
                parts.append("d.*")

        # FROM
        parts.append(f"FROM {self.keyspace} AS d")

        # USE KEYS
        if self._use_keys:
            if len(self._use_keys) == 1:
                placeholder = self.add_param(self._use_keys[0])
                parts.append(f"USE KEYS {placeholder}")
            else:
                placeholder = self.add_param(self._use_keys)
                parts.append(f"USE KEYS {placeholder}")

        # WHERE
        if self._where_clauses:
            parts.append("WHERE " + " AND ".join(f"({c})" for c in self._where_clauses))

        # ORDER BY
        if self._order_by:
            order_parts = []
            for field in self._order_by:
                if field.startswith("-"):
                    order_parts.append(f"d.`{field[1:]}` DESC")
                else:
                    order_parts.append(f"d.`{field}` ASC")
            parts.append("ORDER BY " + ", ".join(order_parts))

        # LIMIT
        if self._limit is not None:
            placeholder = self.add_param(self._limit)
            parts.append(f"LIMIT {placeholder}")

        # OFFSET
        if self._offset is not None:
            placeholder = self.add_param(self._offset)
            parts.append(f"OFFSET {placeholder}")

        return " ".join(parts), self._params

    def build_update(self, updates: dict[str, Any]) -> tuple[str, list[Any]]:
        """Build a N1QL UPDATE statement.

        Args:
            updates: Dict of field_name -> new_value.

        Returns:
            A tuple of (statement_string, positional_parameters).
        """
        set_clauses = []
        for field, value in updates.items():
            _validate_identifier(field)
            placeholder = self.add_param(value)
            set_clauses.append(f"d.`{field}` = {placeholder}")

        parts = [f"UPDATE {self.keyspace} AS d"]

        if self._use_keys:
            if len(self._use_keys) == 1:
                placeholder = self.add_param(self._use_keys[0])
                parts.append(f"USE KEYS {placeholder}")
            else:
                placeholder = self.add_param(self._use_keys)
                parts.append(f"USE KEYS {placeholder}")

        parts.append("SET " + ", ".join(set_clauses))

        if self._where_clauses:
            parts.append("WHERE " + " AND ".join(f"({c})" for c in self._where_clauses))

        return " ".join(parts), self._params

    def build_delete(self) -> tuple[str, list[Any]]:
        """Build a N1QL DELETE statement.

        Returns:
            A tuple of (statement_string, positional_parameters).
        """
        parts = [f"DELETE FROM {self.keyspace} AS d"]

        if self._use_keys:
            if len(self._use_keys) == 1:
                placeholder = self.add_param(self._use_keys[0])
                parts.append(f"USE KEYS {placeholder}")
            else:
                placeholder = self.add_param(self._use_keys)
                parts.append(f"USE KEYS {placeholder}")

        if self._where_clauses:
            parts.append("WHERE " + " AND ".join(f"({c})" for c in self._where_clauses))

        return " ".join(parts), self._params
