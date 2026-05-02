"""Couchbase database backend feature flags."""

from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    minimum_database_version = (7, 0)

    # Couchbase uses string document keys (UUIDs), not auto-increment integers.
    supports_unspecified_pk = False
    allows_auto_pk_0 = False

    # Couchbase 7.0+ supports ACID transactions via N1QL BEGIN/COMMIT/ROLLBACK.
    # Reflects the runtime configuration: OPTIONS["TRANSACTIONS"]="disabled"
    # turns this off so Django (and tests) treat the backend as non-transactional.
    @property
    def supports_transactions(self):
        mode = self.connection.settings_dict.get("OPTIONS", {}).get("TRANSACTIONS", "enabled")
        return str(mode).lower() != "disabled"

    @property
    def atomic_transactions(self):
        return self.supports_transactions

    uses_savepoints = False
    can_release_savepoints = False
    can_rollback_ddl = False

    # No SELECT FOR UPDATE in N1QL.
    has_select_for_update = False
    has_select_for_update_nowait = False
    has_select_for_update_skip_locked = False
    has_select_for_update_of = False

    # FK constraints are application-level, not enforced by Couchbase.
    supports_foreign_keys = False
    can_create_inline_fk = False
    can_introspect_foreign_keys = False
    indexes_foreign_keys = False
    can_defer_constraint_checks = False
    supports_forward_references = True

    # Couchbase doesn't enforce CHECK constraints.
    supports_column_check_constraints = False
    supports_table_check_constraints = False
    can_introspect_check_constraints = False

    # Couchbase is schemaless — no column-level operations.
    supports_combined_alters = False
    connection_persists_old_columns = False
    can_introspect_default = False

    # Couchbase supports RETURNING clause in DML.
    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False

    # N1QL supports bulk insert via multi-value INSERT.
    has_bulk_insert = True

    # JSON is native in Couchbase.
    supports_json_field = True
    can_introspect_json_field = True
    supports_primitives_in_json_field = True
    has_native_json_field = True

    # N1QL uses positional parameters ($1, $2, ...), not pyformat.
    supports_paramstyle_pyformat = False

    # Schema is implicit — defaults are handled at application level.
    requires_literal_defaults = False
    supports_expression_defaults = False
    supports_default_keyword_in_insert = False
    supports_default_keyword_in_bulk_insert = False

    # N1QL has UNION/INTERSECT/EXCEPT, partial/expression indexes, and OVER()
    # at the SQL level, but the cursor's regex SQL rewriter has not been
    # exercised against the SQL Django emits for these features. Advertising
    # them as supported makes Django generate queries the rewriter mishandles.
    #
    # supports_select_union is on because Wagtail's site-history admin
    # (and other Django consumers) emit UNION queries that the cursor handles
    # correctly today — the live wagtail_crud test suite is the integration
    # coverage. The other flags below have no such coverage and stay off
    # until each gets a tested rewrite path.
    supports_select_union = True
    supports_select_intersection = False
    supports_select_difference = False
    supports_partial_indexes = False
    supports_expression_indexes = False
    supports_over_clause = False

    # N1QL supports DISTINCT.
    can_distinct_on_fields = False

    # Couchbase stores strings — no separate REAL type.
    has_real_datatype = False
    has_native_uuid_field = False
    has_native_duration_field = False
    supports_temporal_subtraction = False

    # N1QL REGEXP_CONTAINS supports backreferences.
    supports_regex_backreferencing = True

    # N1QL supports date string lookups.
    supports_date_lookup_using_string = True

    # Couchbase stores ISO 8601 strings with UTC offset (+00:00).
    supports_timezones = True
    has_zoneinfo_database = False

    # N1QL doesn't have FILTER clause in aggregates.
    supports_aggregate_filter_clause = False

    # Couchbase supports index on text fields.
    supports_index_on_text_field = True

    # N1QL supports NULLS FIRST/LAST.
    supports_order_by_nulls_modifier = True

    # Couchbase has no sequence concept.
    supports_sequence_reset = False

    # ignore_conflicts is emulated via a best-effort SELECT-then-INSERT in
    # SQLInsertCompiler — that pre-check is race-prone for non-PK uniques,
    # so we only advertise PK-level support. update_conflicts is not
    # implemented (would require ON CONFLICT semantics N1QL lacks).
    supports_ignore_conflicts = True
    supports_update_conflicts = False

    # Collation is not supported at field level in Couchbase.
    supports_collation_on_charfield = False
    supports_collation_on_textfield = False

    # No column/table comments in Couchbase.
    supports_comments = False

    # No generated columns.
    supports_stored_generated_columns = False
    supports_virtual_generated_columns = False

    # Couchbase has no character limit on fields.
    supports_unlimited_charfield = True

    # Test support.
    test_db_allows_multiple_connections = True
    can_clone_databases = False

    # Use the schema editor's client-side param binding.
    schema_editor_uses_clientside_param_binding = True
