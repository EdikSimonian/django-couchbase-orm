"""Couchbase schema editor — creates/drops collections and indexes."""

from __future__ import annotations

import logging

from django.db.backends.base.schema import BaseDatabaseSchemaEditor

logger = logging.getLogger("django.db.backends.couchbase.schema")


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    # Couchbase is schemaless — most SQL DDL templates are not applicable.
    # We override the methods that matter instead of using SQL templates.

    # Override SQL templates — Couchbase uses N1QL, not DDL SQL.
    sql_create_table = None
    sql_delete_table = None
    sql_create_column = None
    sql_alter_column = None
    sql_delete_column = None
    sql_rename_column = None
    sql_create_unique = None
    sql_delete_unique = None
    sql_create_fk = None
    sql_create_check = None
    sql_delete_check = None
    sql_create_index = None
    sql_delete_index = None

    def __init__(self, connection, collect_sql=False, atomic=True):
        # Couchbase doesn't support DDL transactions, so always non-atomic.
        super().__init__(connection, collect_sql=collect_sql, atomic=False)

    def _get_bucket_and_scope(self):
        bucket_name = self.connection.settings_dict["NAME"]
        scope_name = self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default")
        return bucket_name, scope_name

    def _collection_exists(self, bucket, scope_name, collection_name):
        """Check if a collection already exists."""
        try:
            cm = bucket.collections()
            for scope in cm.get_all_scopes():
                if scope.name == scope_name:
                    for col in scope.collections:
                        if col.name == collection_name:
                            return True
        except Exception as e:
            logger.warning("Error checking collection existence for %s.%s: %s", scope_name, collection_name, e)
        return False

    def _create_collection_and_index(self, collection_name):
        """Create a Couchbase collection and its primary index."""
        bucket_name, scope_name = self._get_bucket_and_scope()
        self.connection.ensure_connection()
        bucket = self.connection.couchbase_bucket

        if self._collection_exists(bucket, scope_name, collection_name):
            logger.debug(
                "Collection %s.%s already exists, skipping creation",
                scope_name,
                collection_name,
            )
            return

        # Create scope if not _default.
        if scope_name != "_default":
            try:
                cm = bucket.collections()
                cm.create_scope(scope_name)
            except Exception as e:
                err = str(e).lower()
                if "already exists" not in err:
                    logger.warning("Error creating scope '%s': %s", scope_name, e)

        # Create collection.
        try:
            from couchbase.management.collections import CollectionSpec

            cm = bucket.collections()
            cm.create_collection(CollectionSpec(collection_name, scope_name))
            logger.info("Created collection %s.%s", scope_name, collection_name)
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug("Collection %s.%s already exists", scope_name, collection_name)
            else:
                raise

        # Create primary index — retry because the collection may not be
        # queryable immediately after creation.
        import time

        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"
        index_sql = f"CREATE PRIMARY INDEX IF NOT EXISTS ON {keyspace}"

        for attempt in range(10):
            try:
                self.connection.couchbase_cluster.query(index_sql).execute()
                logger.info("Created primary index on %s", collection_name)
                break
            except Exception as e:
                if attempt < 9 and "12003" in str(e):
                    time.sleep(0.5)
                    continue
                logger.warning(
                    "Could not create primary index on %s: %s",
                    collection_name,
                    e,
                )

    def create_model(self, model):
        """Create a Couchbase collection for the model and any M2M tables."""
        self._create_collection_and_index(model._meta.db_table)

        # Create indexes for unique fields.
        for field in model._meta.local_fields:
            if field.unique and not field.primary_key:
                self._create_unique_index(model, [field])

        # Create M2M through tables.
        for field in model._meta.local_many_to_many:
            if field.remote_field.through._meta.auto_created:
                self.create_model(field.remote_field.through)

    def delete_model(self, model):
        """Drop a Couchbase collection and any M2M through tables."""
        # Delete M2M through tables first.
        for field in model._meta.local_many_to_many:
            if field.remote_field.through._meta.auto_created:
                self.delete_model(field.remote_field.through)

        collection_name = model._meta.db_table
        bucket_name, scope_name = self._get_bucket_and_scope()

        self.connection.ensure_connection()
        bucket = self.connection.couchbase_bucket

        try:
            from couchbase.management.collections import CollectionSpec

            cm = bucket.collections()
            cm.drop_collection(CollectionSpec(collection_name, scope_name))
            logger.info("Dropped collection %s.%s", scope_name, collection_name)
        except Exception as e:
            logger.warning("Could not drop collection %s: %s", collection_name, e)

    def add_field(self, model, field):
        """Add a field — mostly a no-op for schemaless Couchbase.

        For M2M fields, creates the through-table collection.
        For unique fields, creates a unique index.
        """
        # M2M fields need their through-table collection created.
        if field.many_to_many:
            through = field.remote_field.through
            if through._meta.auto_created:
                self.create_model(through)
            return

        # Create unique index if needed.
        if field.unique and not field.primary_key:
            self._create_unique_index(model, [field])

    def remove_field(self, model, field):
        """Remove a field — no-op for schemaless Couchbase.

        For M2M fields, drops the through-table collection.
        """
        if field.many_to_many:
            through = field.remote_field.through
            if through._meta.auto_created:
                self.delete_model(through)
            return

    def alter_field(self, model, old_field, new_field, strict=False):
        """Alter a field — mostly no-op. Handle unique constraint changes."""
        if old_field.unique and not new_field.unique:
            # Drop unique index.
            self._drop_unique_index(model, [old_field])
        elif not old_field.unique and new_field.unique:
            # Create unique index.
            self._create_unique_index(model, [new_field])

    def _create_unique_index(self, model, fields):
        """Create a non-unique N1QL index that backs application-level unique checks.

        N1QL has no UNIQUE INDEX type — uniqueness on non-PK fields cannot be
        enforced by Couchbase. The index here only speeds up the best-effort
        SELECT used by SQLInsertCompiler._find_existing_by_unique. PK uniqueness
        is enforced by the KV engine via INSERT semantics.
        """
        collection_name = model._meta.db_table
        bucket_name, scope_name = self._get_bucket_and_scope()
        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"

        col_names = [f.column for f in fields]
        index_name = "uniq_{}_{}".format(collection_name, "_".join(col_names))
        cols_sql = ", ".join(qn(c) for c in col_names)

        sql = f"CREATE INDEX {qn(index_name)} ON {keyspace} ({cols_sql})"
        try:
            self.connection.ensure_connection()
            self.connection.couchbase_cluster.query(sql).execute()
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                logger.warning(
                    "Could not create best-effort uniqueness lookup index %s: %s",
                    index_name,
                    e,
                )

    def _drop_unique_index(self, model, fields):
        """Drop a unique index."""
        collection_name = model._meta.db_table
        bucket_name, scope_name = self._get_bucket_and_scope()
        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"

        col_names = [f.column for f in fields]
        index_name = "uniq_{}_{}".format(collection_name, "_".join(col_names))

        sql = f"DROP INDEX {qn(index_name)} ON {keyspace}"
        try:
            self.connection.ensure_connection()
            self.connection.couchbase_cluster.query(sql).execute()
        except Exception as e:
            err = str(e).lower()
            if "not found" not in err and "12004" not in str(e):
                logger.warning("Error dropping unique index %s: %s", index_name, e)

    def add_index(self, model, index):
        """Create a secondary N1QL index."""
        collection_name = model._meta.db_table
        bucket_name, scope_name = self._get_bucket_and_scope()
        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"

        col_names = [model._meta.get_field(field_name).column for field_name in index.fields]
        index_name = index.name or "idx_{}_{}".format(
            collection_name,
            "_".join(col_names),
        )
        cols_sql = ", ".join(qn(c) for c in col_names)

        sql = f"CREATE INDEX IF NOT EXISTS {qn(index_name)} ON {keyspace} ({cols_sql})"
        import time

        for attempt in range(3):
            try:
                self.connection.ensure_connection()
                self.connection.couchbase_cluster.query(sql).execute()
                break
            except Exception as e:
                err = str(e).lower()
                if "already exists" in err or "12003" in str(e):
                    logger.warning("Index creation skipped for %s: %s", index_name, e)
                    break
                if "transient" in err or "build already in progress" in err:
                    logger.warning("Transient error creating index %s (attempt %d): %s", index_name, attempt + 1, e)
                    if attempt < 2:
                        time.sleep(3)
                        continue
                    logger.warning("Index %s will be built in background by Couchbase", index_name)
                    break
                raise

    def remove_index(self, model, index):
        """Drop a secondary N1QL index."""
        collection_name = model._meta.db_table
        bucket_name, scope_name = self._get_bucket_and_scope()
        qn = self.connection.ops.quote_name
        keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"

        index_name = index.name or "idx_{}_{}".format(
            collection_name,
            "_".join(index.fields),
        )
        sql = f"DROP INDEX {qn(index_name)} ON {keyspace}"
        try:
            self.connection.ensure_connection()
            self.connection.couchbase_cluster.query(sql).execute()
        except Exception as e:
            err = str(e).lower()
            if "not found" not in err and "12004" not in str(e):
                logger.warning("Error dropping index %s: %s", index_name, e)

    def add_constraint(self, model, constraint):
        """Handle constraints — create unique index for UniqueConstraint."""
        from django.db.models.constraints import UniqueConstraint

        if isinstance(constraint, UniqueConstraint):
            fields = [model._meta.get_field(field_name) for field_name in constraint.fields]
            self._create_unique_index(model, fields)

    def remove_constraint(self, model, constraint):
        """Remove constraint — drop unique index."""
        from django.db.models.constraints import UniqueConstraint

        if isinstance(constraint, UniqueConstraint):
            fields = [model._meta.get_field(field_name) for field_name in constraint.fields]
            self._drop_unique_index(model, fields)

    def alter_unique_together(self, model, old_unique_together, new_unique_together):
        """Handle unique_together changes via N1QL indexes."""
        olds = {tuple(fields) for fields in old_unique_together}
        news = {tuple(fields) for fields in new_unique_together}

        # Remove old constraints.
        for fields in olds - news:
            field_objs = [model._meta.get_field(f) for f in fields]
            self._drop_unique_index(model, field_objs)

        # Add new constraints.
        for fields in news - olds:
            field_objs = [model._meta.get_field(f) for f in fields]
            self._create_unique_index(model, field_objs)

    def alter_index_together(self, model, old_index_together, new_index_together):
        """Handle index_together changes via N1QL indexes."""
        olds = {tuple(fields) for fields in old_index_together}
        news = {tuple(fields) for fields in new_index_together}

        for fields in olds - news:
            field_objs = [model._meta.get_field(f) for f in fields]
            self._drop_unique_index(model, field_objs)

        for fields in news - olds:
            collection_name = model._meta.db_table
            bucket_name, scope_name = self._get_bucket_and_scope()
            qn = self.connection.ops.quote_name
            keyspace = f"{qn(bucket_name)}.{qn(scope_name)}.{qn(collection_name)}"
            col_names = [model._meta.get_field(f).column for f in fields]
            index_name = "idx_{}_{}".format(collection_name, "_".join(col_names))
            cols_sql = ", ".join(qn(c) for c in col_names)
            sql = f"CREATE INDEX IF NOT EXISTS {qn(index_name)} ON {keyspace} ({cols_sql})"
            try:
                self.connection.ensure_connection()
                self.connection.couchbase_cluster.query(sql).execute()
            except Exception as e:
                err = str(e).lower()
                if "already exists" not in err:
                    logger.warning("Error creating index %s: %s", index_name, e)

    def _create_unique_sql(
        self,
        model,
        fields,
        name=None,
        condition=None,
        deferrable=None,
        include=None,
        opclasses=None,
        expressions=None,
    ):
        """Override to return None — unique constraints are handled by _create_unique_index."""
        if fields:
            field_objs = [model._meta.get_field(f) if isinstance(f, str) else f for f in fields]
            self._create_unique_index(model, field_objs)
        return None

    def _delete_unique_sql(
        self,
        model,
        name,
        condition=None,
        deferrable=None,
        include=None,
        opclasses=None,
        expressions=None,
    ):
        """Override to return None."""
        return None

    def _create_fk_sql(self, model, field, suffix):
        """No FK constraints in Couchbase."""
        return None

    def _create_check_sql(self, model, name, check):
        """No CHECK constraints in Couchbase."""
        return None

    def alter_db_table(self, model, old_db_table, new_db_table):
        """Handle table rename by creating the new collection.

        Couchbase doesn't support renaming collections. We create the new
        collection and leave the old one (data migration should be handled
        separately). For fresh installs this is fine since both are empty.
        """
        if old_db_table == new_db_table:
            return
        logger.info(
            "Creating new collection %s (rename from %s)",
            new_db_table,
            old_db_table,
        )
        self._create_collection_and_index(new_db_table)

    def execute(self, sql, params=()):
        """Execute a DDL statement via N1QL."""
        if sql is None:
            return
        # Convert %s placeholders if needed.
        if params:
            sql = sql % tuple(
                "'{}'".format(str(p).replace("'", "''")) if isinstance(p, str) else str(p) for p in params
            )
        try:
            self.connection.ensure_connection()
            self.connection.couchbase_cluster.query(sql).execute()
        except Exception as e:
            logger.error("Schema DDL error: %s\nSQL: %s", e, sql)
            raise
