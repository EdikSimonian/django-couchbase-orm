"""Lazy, chainable QuerySet for Couchbase documents."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from django_couchbase_orm.query.n1ql import N1QLQuery
from django_couchbase_orm.queryset.q import Q
from django_couchbase_orm.queryset.transform import apply_lookup

if TYPE_CHECKING:
    from django_couchbase_orm.document import Document


def _get_scan_consistency(alias: str = "default"):
    """Get the configured scan consistency level for the given alias.

    Configurable via COUCHBASE settings:
        COUCHBASE = {
            "default": {
                ...
                "SCAN_CONSISTENCY": "request_plus",  # or "not_bounded"
            }
        }

    Defaults to REQUEST_PLUS (strong consistency).
    """
    from couchbase.n1ql import QueryScanConsistency

    from django_couchbase_orm.connection import _get_config

    try:
        config = _get_config(alias)
        level = config.get("SCAN_CONSISTENCY", "request_plus").lower()
        if level == "not_bounded":
            return QueryScanConsistency.NOT_BOUNDED
    except Exception:
        pass
    return QueryScanConsistency.REQUEST_PLUS


class QuerySet:
    """A lazy, chainable QuerySet that builds N1QL queries.

    Queries are not executed until the QuerySet is iterated, sliced, or
    explicitly evaluated (count, first, get, exists, etc.).
    """

    def __init__(self, document_class: type[Document]):
        self._document_class = document_class
        self._filters: list[Q | tuple[str, Any]] = []
        self._excludes: list[Q | tuple[str, Any]] = []
        self._order_by_fields: list[str] = []
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._values_fields: list[str] | None = None  # None = return Documents
        self._select_related_fields: list[str] = []
        self._result_cache: list | None = None

    def _clone(self) -> QuerySet:
        """Create a copy of this QuerySet."""
        qs = QuerySet(self._document_class)
        qs._filters = self._filters[:]
        qs._excludes = self._excludes[:]
        qs._order_by_fields = self._order_by_fields[:]
        qs._limit_val = self._limit_val
        qs._offset_val = self._offset_val
        qs._values_fields = self._values_fields[:] if self._values_fields is not None else None
        qs._select_related_fields = self._select_related_fields[:]
        return qs

    @property
    def _meta(self):
        return self._document_class._meta

    def _get_field_map(self) -> dict[str, str]:
        """Map Python field names to their db_field names."""
        return {name: field.get_db_field() for name, field in self._meta.fields.items()}

    def _build_query(self) -> N1QLQuery:
        """Build the N1QL query from current QuerySet state."""
        from django_couchbase_orm.connection import _get_config

        config = _get_config(self._meta.bucket_alias)
        query = N1QLQuery(
            bucket=config["BUCKET"],
            scope=self._meta.scope_name,
            collection=self._meta.collection_name,
        )

        query.include_meta_id()

        # Select specific fields or all
        if self._values_fields is not None:
            field_map = self._get_field_map()
            db_fields = [field_map.get(f, f) for f in self._values_fields]
            query.select(*db_fields)
            query.include_meta_id()

        # Add type discriminator filter
        type_field = self._meta.doc_type_field
        type_value = self._meta.doc_type_value
        placeholder = query.add_param(type_value)
        query.where(f"d.`{type_field}` = {placeholder}")

        # Apply filters
        field_map = self._get_field_map()
        for f in self._filters:
            if isinstance(f, Q):
                clause = f.resolve(query, field_map)
                if clause:
                    query.where(clause)
            else:
                field_expr, value = f
                # Map field name to db_field
                base_field = field_expr.split("__")[0]
                if base_field in field_map and field_map[base_field] != base_field:
                    field_expr = field_map[base_field] + field_expr[len(base_field) :]
                clause = apply_lookup(query, field_expr, value)
                query.where(clause)

        # Apply excludes (as NOT)
        for f in self._excludes:
            if isinstance(f, Q):
                clause = f.resolve(query, field_map)
                if clause:
                    query.where(f"NOT ({clause})")
            else:
                field_expr, value = f
                base_field = field_expr.split("__")[0]
                if base_field in field_map and field_map[base_field] != base_field:
                    field_expr = field_map[base_field] + field_expr[len(base_field) :]
                clause = apply_lookup(query, field_expr, value)
                query.where(f"NOT ({clause})")

        # ORDER BY
        if self._order_by_fields:
            # Map field names to db_field names
            mapped_order = []
            for field in self._order_by_fields:
                desc = field.startswith("-")
                name = field[1:] if desc else field
                db_name = field_map.get(name, name)
                mapped_order.append(f"-{db_name}" if desc else db_name)
            query.order_by(*mapped_order)

        # LIMIT / OFFSET
        if self._limit_val is not None:
            query.limit(self._limit_val)
        if self._offset_val is not None:
            query.offset(self._offset_val)

        return query

    def _execute(self) -> list:
        """Execute the query and return results."""
        if self._result_cache is not None:
            return self._result_cache

        query = self._build_query()
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                adhoc=False,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )

        if self._values_fields is not None:
            self._result_cache = list(result)
        else:
            documents = []
            for row in result:
                doc_id = row.pop("__id", None)
                cas = row.pop("__cas", None)
                if doc_id:
                    documents.append(self._document_class.from_dict(doc_id, row, cas=cas))
                else:
                    documents.append(row)
            # Prefetch referenced documents for select_related
            if self._select_related_fields and documents:
                self._prefetch_related(documents)
            self._result_cache = documents

        return self._result_cache

    def _prefetch_related(self, documents: list) -> None:
        """Prefetch referenced documents to avoid N+1 queries."""
        from django_couchbase_orm.fields.reference import ReferenceField

        for field_name in self._select_related_fields:
            field = self._meta.fields.get(field_name)
            if not field or not isinstance(field, ReferenceField):
                continue

            # Collect all unique keys
            keys = set()
            for doc in documents:
                key = doc._data.get(field_name)
                if key:
                    keys.add(key)

            if not keys:
                continue

            # Batch-fetch all referenced documents via KV multi-get
            ref_class = field._resolve_type()
            ref_cache = {}
            from django_couchbase_orm.connection import get_collection

            collection = get_collection(
                alias=ref_class._meta.bucket_alias,
                scope=ref_class._meta.scope_name,
                collection=ref_class._meta.collection_name,
            )
            from couchbase.exceptions import DocumentNotFoundException

            for key in keys:
                try:
                    result = collection.get(key)
                    data = result.content_as[dict]
                    ref_cache[key] = ref_class.from_dict(key, data, cas=result.cas)
                except DocumentNotFoundException:
                    # Dangling reference is a legitimate "skip" — leaves the
                    # _prefetched cache without an entry for this key, and
                    # the caller can detect missing FK via doc._data[field_name].
                    continue

            # Attach prefetched docs as _prefetched_{field_name}
            for doc in documents:
                key = doc._data.get(field_name)
                if key and key in ref_cache:
                    doc._prefetched = getattr(doc, "_prefetched", {})
                    doc._prefetched[field_name] = ref_cache[key]

    # ============================================================
    # Chainable methods (return new QuerySet)
    # ============================================================

    def filter(self, *args: Q, **kwargs) -> QuerySet:
        """Filter documents matching the given conditions."""
        qs = self._clone()
        for q_obj in args:
            qs._filters.append(q_obj)
        for key, value in kwargs.items():
            qs._filters.append((key, value))
        return qs

    def exclude(self, *args: Q, **kwargs) -> QuerySet:
        """Exclude documents matching the given conditions."""
        qs = self._clone()
        for q_obj in args:
            qs._excludes.append(q_obj)
        for key, value in kwargs.items():
            qs._excludes.append((key, value))
        return qs

    def order_by(self, *fields: str) -> QuerySet:
        """Set ordering. Prefix with '-' for descending."""
        qs = self._clone()
        qs._order_by_fields = list(fields)
        return qs

    def select_related(self, *fields: str) -> QuerySet:
        """Prefetch referenced documents to avoid N+1 queries.

        Args:
            fields: ReferenceField names to prefetch.
        """
        qs = self._clone()
        qs._select_related_fields = list(fields)
        return qs

    def values(self, *fields: str) -> QuerySet:
        """Return dicts with specified fields instead of Document instances."""
        qs = self._clone()
        qs._values_fields = list(fields) if fields else []
        return qs

    def all(self) -> QuerySet:
        """Return a clone of this QuerySet (no filters added)."""
        return self._clone()

    def none(self) -> QuerySet:
        """Return an empty QuerySet."""
        qs = self._clone()
        qs._result_cache = []
        return qs

    # ============================================================
    # Slicing (LIMIT / OFFSET)
    # ============================================================

    def __getitem__(self, key):
        if isinstance(key, slice):
            qs = self._clone()
            start = key.start or 0
            stop = key.stop
            if start:
                qs._offset_val = start
            if stop is not None:
                qs._limit_val = stop - start
            return qs
        elif isinstance(key, int):
            if key < 0:
                raise ValueError("Negative indexing is not supported.")
            qs = self._clone()
            qs._offset_val = key
            qs._limit_val = 1
            results = qs._execute()
            if results:
                return results[0]
            raise IndexError("QuerySet index out of range")
        raise TypeError(f"QuerySet indices must be integers or slices, not {type(key).__name__}")

    # ============================================================
    # Terminal methods (execute the query)
    # ============================================================

    def __iter__(self) -> Iterator:
        return iter(self._execute())

    def __len__(self) -> int:
        return len(self._execute())

    def __bool__(self) -> bool:
        return bool(self._execute())

    def __repr__(self) -> str:
        # Limit display to avoid huge output
        data = list(self[:21])
        if len(data) > 20:
            return f"<QuerySet [{', '.join(repr(d) for d in data[:20])}, ...]>"
        return f"<QuerySet [{', '.join(repr(d) for d in data)}]>"

    def count(self) -> int:
        """Return the count of matching documents using COUNT(*)."""
        if self._result_cache is not None:
            return len(self._result_cache)
        query = self._build_query()
        query.select_count()
        query._order_by = []  # No ordering needed for count
        query._limit = None
        query._offset = None
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                adhoc=False,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )
        for row in result:
            return row.get("__count", 0)
        return 0

    def aggregate(self, **kwargs) -> dict:
        """Run aggregation functions on the QuerySet.

        Supported functions: Count, Sum, Avg, Min, Max.

        Usage:
            Beer.objects.filter(style="IPA").aggregate(
                avg_abv=Avg("abv"),
                max_abv=Max("abv"),
                total=Count("name"),
            )
            # Returns: {"avg_abv": 6.5, "max_abv": 12.0, "total": 150}
        """
        from django_couchbase_orm.aggregates import _build_agg_expression
        from django_couchbase_orm.query.n1ql import _validate_identifier

        query = self._build_query()
        query._order_by = []
        query._limit = None
        query._offset = None

        # Build SELECT clause with aggregate expressions
        field_map = self._get_field_map()
        select_parts = []
        for alias, agg in kwargs.items():
            _validate_identifier(alias)
            expr = _build_agg_expression(agg, field_map)
            select_parts.append(f"{expr} AS `{alias}`")

        query._select_raw = ", ".join(select_parts)
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )
        for row in result:
            return dict(row)
        return {alias: None for alias in kwargs}

    def exists(self) -> bool:
        """Return True if the QuerySet contains any results."""
        if self._result_cache is not None:
            return len(self._result_cache) > 0
        qs = self._clone()
        qs._limit_val = 1
        return len(qs._execute()) > 0

    def first(self) -> Document | None:
        """Return the first result, or None if empty."""
        qs = self._clone()
        qs._limit_val = 1
        results = qs._execute()
        return results[0] if results else None

    def last(self) -> Document | None:
        """Return the last result, or None if empty.

        Note: requires the QuerySet to be ordered. If unordered, results are arbitrary.
        """
        results = self._execute()
        return results[-1] if results else None

    def get(self, *args: Q, **kwargs) -> Document:
        """Return exactly one document matching the conditions.

        Raises DoesNotExist if no match, MultipleObjectsReturned if more than one.
        """
        qs = self.filter(*args, **kwargs) if args or kwargs else self._clone()
        qs._limit_val = 2  # Fetch 2 to detect multiple
        results = qs._execute()

        if not results:
            raise self._document_class.DoesNotExist(f"{self._document_class.__name__} matching query does not exist.")
        if len(results) > 1:
            raise self._document_class.MultipleObjectsReturned(
                f"get() returned more than one {self._document_class.__name__}."
            )
        return results[0]

    def create(self, **kwargs) -> Document:
        """Create and save a new document."""
        from django_couchbase_orm.queryset.manager import DocumentManager

        manager = DocumentManager()
        manager._document_class = self._document_class
        return manager.create(**kwargs)

    def update(self, **kwargs) -> int:
        """Bulk update all matching documents. Returns the number of affected rows.

        Uses N1QL UPDATE statement.
        """
        if not kwargs:
            return 0

        # Map field names to db_field names
        field_map = self._get_field_map()
        db_updates = {}
        for key, value in kwargs.items():
            db_field = field_map.get(key, key)
            field_obj = self._meta.fields.get(key)
            if field_obj:
                db_updates[db_field] = field_obj.to_json(value)
            else:
                db_updates[db_field] = value

        query = self._build_query()
        statement, params = query.build_update(db_updates)

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
                metrics=True,
            ),
        )
        # Consume the result to execute the query
        rows = list(result)
        meta = result.metadata()
        metrics = meta.metrics()
        if metrics:
            return int(metrics.mutation_count())
        return len(rows)

    def delete(self) -> int:
        """Bulk delete all matching documents. Returns the number of deleted documents.

        Uses N1QL DELETE statement.
        """
        query = self._build_query()
        statement, params = query.build_delete()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
                metrics=True,
            ),
        )
        rows = list(result)
        meta = result.metadata()
        metrics = meta.metrics()
        if metrics:
            return int(metrics.mutation_count())
        return len(rows)

    def raw(self, statement: str, params: list | None = None) -> list:
        """Execute a raw N1QL query and return results as a list of dicts."""
        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        opts = QueryOptions(
            positional_parameters=params if params else None,
            scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
        )
        result = cluster.query(statement, opts)
        return list(result)

    def iterator(self) -> Iterator:
        """Return an iterator that doesn't cache results.

        Useful for large result sets to avoid loading everything into memory.
        """
        query = self._build_query()
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )

        for row in result:
            doc_id = row.pop("__id", None)
            cas = row.pop("__cas", None)
            if doc_id:
                yield self._document_class.from_dict(doc_id, row, cas=cas)
            else:
                yield row

    # ============================================================
    # Async methods
    # ============================================================

    async def _async_execute(self) -> list:
        """Execute the query asynchronously and return results."""
        if self._result_cache is not None:
            return self._result_cache

        query = self._build_query()
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.async_connection import get_async_cluster

        cluster = await get_async_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                adhoc=False,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )

        if self._values_fields is not None:
            self._result_cache = [row async for row in result]
        else:
            documents = []
            async for row in result:
                doc_id = row.pop("__id", None)
                cas = row.pop("__cas", None)
                if doc_id:
                    documents.append(self._document_class.from_dict(doc_id, row, cas=cas))
                else:
                    documents.append(row)
            if self._select_related_fields and documents:
                await self._async_prefetch_related(documents)
            self._result_cache = documents

        return self._result_cache

    async def _async_prefetch_related(self, documents: list) -> None:
        """Async version of _prefetch_related."""
        from django_couchbase_orm.async_connection import get_async_collection
        from django_couchbase_orm.fields.reference import ReferenceField

        for field_name in self._select_related_fields:
            field = self._meta.fields.get(field_name)
            if not field or not isinstance(field, ReferenceField):
                continue

            keys = {doc._data.get(field_name) for doc in documents if doc._data.get(field_name)}
            if not keys:
                continue

            ref_class = field._resolve_type()
            collection = await get_async_collection(
                alias=ref_class._meta.bucket_alias,
                scope=ref_class._meta.scope_name,
                collection=ref_class._meta.collection_name,
            )

            ref_cache = {}
            from couchbase.exceptions import DocumentNotFoundException

            for key in keys:
                try:
                    result = await collection.get(key)
                    data = result.content_as[dict]
                    ref_cache[key] = ref_class.from_dict(key, data, cas=result.cas)
                except DocumentNotFoundException:
                    # Dangling reference — leave the slot empty. All other
                    # exceptions (auth, connection, timeout) propagate.
                    continue

            for doc in documents:
                key = doc._data.get(field_name)
                if key and key in ref_cache:
                    doc._prefetched = getattr(doc, "_prefetched", {})
                    doc._prefetched[field_name] = ref_cache[key]

    async def acount(self) -> int:
        """Async version of count()."""
        if self._result_cache is not None:
            return len(self._result_cache)
        query = self._build_query()
        query.select_count()
        query._order_by = []
        query._limit = None
        query._offset = None
        statement, params = query.build()

        from couchbase.options import QueryOptions

        from django_couchbase_orm.async_connection import get_async_cluster

        cluster = await get_async_cluster(self._meta.bucket_alias)
        result = cluster.query(
            statement,
            QueryOptions(
                positional_parameters=params,
                adhoc=False,
                scan_consistency=_get_scan_consistency(self._meta.bucket_alias),
            ),
        )
        async for row in result:
            return row.get("__count", 0)
        return 0

    async def aexists(self) -> bool:
        """Async version of exists()."""
        if self._result_cache is not None:
            return len(self._result_cache) > 0
        qs = self._clone()
        qs._limit_val = 1
        results = await qs._async_execute()
        return len(results) > 0

    async def afirst(self) -> Document | None:
        """Async version of first()."""
        qs = self._clone()
        qs._limit_val = 1
        results = await qs._async_execute()
        return results[0] if results else None

    async def aget(self, *args: Q, **kwargs) -> Document:
        """Async version of get()."""
        qs = self.filter(*args, **kwargs) if args or kwargs else self._clone()
        qs._limit_val = 2
        results = await qs._async_execute()

        if not results:
            raise self._document_class.DoesNotExist(f"{self._document_class.__name__} matching query does not exist.")
        if len(results) > 1:
            raise self._document_class.MultipleObjectsReturned(
                f"get() returned more than one {self._document_class.__name__}."
            )
        return results[0]

    async def alist(self) -> list:
        """Async execution returning a list of results."""
        return await self._async_execute()

    def __aiter__(self):
        """Support async for loops: async for doc in queryset."""
        return self._async_iterator()

    async def _async_iterator(self):
        results = await self._async_execute()
        for item in results:
            yield item
