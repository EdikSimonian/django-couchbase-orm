"""Couchbase database introspection."""

from __future__ import annotations

from collections import namedtuple

from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.backends.base.introspection import FieldInfo, TableInfo


class DatabaseIntrospection(BaseDatabaseIntrospection):
    data_types_reverse = {
        "varchar": "CharField",
        "text": "TextField",
        "integer": "IntegerField",
        "number": "FloatField",
        "boolean": "BooleanField",
        "json": "JSONField",
        "date": "DateField",
        "datetime": "DateTimeField",
    }

    def get_table_list(self, cursor):
        """Return a list of table (collection) names in the current scope."""
        self.connection.ensure_connection()
        bucket = self.connection.couchbase_bucket
        scope_name = self.connection.settings_dict.get("OPTIONS", {}).get(
            "SCOPE", "_default"
        )

        tables = []
        try:
            cm = bucket.collections()
            for scope in cm.get_all_scopes():
                if scope.name == scope_name:
                    for col in scope.collections:
                        tables.append(
                            TableInfo(col.name, "t")
                        )
        except Exception:
            pass
        return tables

    def get_table_description(self, cursor, table_name):
        """Return field descriptions for the given collection.

        Since Couchbase is schemaless, we infer schema from the Django model
        registry. If the model isn't found, sample a document.
        """
        from django.apps import apps

        # Try to find the model that maps to this table.
        for model in apps.get_models():
            if model._meta.db_table == table_name:
                fields = []
                for field in model._meta.local_fields:
                    fields.append(
                        FieldInfo(
                            name=field.column,
                            type_code=field.get_internal_type(),
                            display_size=None,
                            internal_size=getattr(field, "max_length", None),
                            precision=getattr(field, "max_digits", None),
                            scale=getattr(field, "decimal_places", None),
                            null_ok=field.null,
                            default=field.default if field.has_default() else None,
                            collation=None,
                        )
                    )
                return fields

        # Fallback: sample a document from the collection.
        bucket_name = self.connection.settings_dict["NAME"]
        scope_name = self.connection.settings_dict.get("OPTIONS", {}).get(
            "SCOPE", "_default"
        )
        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(table_name)}"

        try:
            result = self.connection.couchbase_cluster.query(
                f"SELECT * FROM {keyspace} LIMIT 1"
            )
            rows = list(result.rows())
            if rows:
                doc = rows[0].get(table_name, rows[0])
                return [
                    FieldInfo(
                        name=key,
                        type_code=type(value).__name__,
                        display_size=None,
                        internal_size=None,
                        precision=None,
                        scale=None,
                        null_ok=True,
                        default=None,
                        collation=None,
                    )
                    for key, value in doc.items()
                ]
        except Exception:
            pass

        return []

    def get_relations(self, cursor, table_name):
        """Return FK relationships. Couchbase has no FK constraints."""
        return {}

    def get_constraints(self, cursor, table_name):
        """Return indexes and constraints for the given collection."""
        bucket_name = self.connection.settings_dict["NAME"]
        scope_name = self.connection.settings_dict.get("OPTIONS", {}).get(
            "SCOPE", "_default"
        )
        constraints = {}

        try:
            self.connection.ensure_connection()
            result = self.connection.couchbase_cluster.query(
                "SELECT * FROM system:indexes "
                "WHERE bucket_id = $1 AND scope_id = $2 AND keyspace_id = $3",
                bucket_name,
                scope_name,
                table_name,
            )
            for row in result.rows():
                idx = row.get("indexes", row)
                name = idx.get("name", "unknown")
                is_primary = idx.get("is_primary", False)
                index_keys = idx.get("index_key", [])
                # Strip backticks from index key expressions.
                columns = [
                    k.strip("`").strip("(").strip(")") for k in index_keys
                ]
                constraints[name] = {
                    "columns": columns,
                    "primary_key": is_primary,
                    "unique": False,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "orders": [],
                    "type": "idx",
                }
        except Exception:
            pass

        return constraints

    def get_sequences(self, cursor, table_name, table_fields=()):
        """Return sequences — Couchbase has none."""
        return []

    def identifier_converter(self, name):
        """Couchbase identifiers are case-sensitive."""
        return name
