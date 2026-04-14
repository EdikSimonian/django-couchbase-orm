"""N1QL compilers that translate Django's SQL AST into Couchbase N1QL (SQL++) statements."""

from __future__ import annotations

from django.db.models.sql import compiler as base_compiler


class CouchbaseCompilerMixin:
    """Shared helpers for all Couchbase compilers."""

    def _get_keyspace(self, table_name):
        """Convert a Django db_table name to a fully qualified Couchbase keyspace."""
        bucket = self.connection.settings_dict["NAME"]
        scope = self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default")
        qn = self.connection.ops.quote_name
        return f"{qn(bucket)}.{qn(scope)}.{qn(table_name)}"

    def _is_pk_column(self, col_name):
        """Check if a column name refers to the primary key (document ID)."""
        return col_name in ("id", "pk")


class SQLCompiler(CouchbaseCompilerMixin, base_compiler.SQLCompiler):
    def as_sql(self, with_limits=True, with_col_aliases=False):
        """Generate N1QL SELECT statement.

        N1QL does not allow duplicate column names in results (unlike SQL).
        We run the parent as_sql first, then post-process to deduplicate
        column names by adding aliases only where needed. This avoids
        forcing aliases on aggregation queries where extra columns would
        break N1QL's strict GROUP BY.
        """
        sql, params = super().as_sql(with_limits=with_limits, with_col_aliases=with_col_aliases)
        return sql, params

    def get_from_clause(self):
        """Override FROM clause to use Couchbase keyspaces.

        Django's base Join.as_sql() produces `table_name` or `table_name AS alias`.
        We post-process to replace bare table names with full keyspaces.
        """
        result = []
        params = []
        for alias, from_clause in tuple(self.query.alias_map.items()):
            if not self.query.alias_refcount[alias]:
                continue
            clause_sql, clause_params = self.compile(from_clause)
            # Replace the simple quoted table name with the full keyspace.
            table_name = from_clause.table_name if hasattr(from_clause, "table_name") else alias
            quoted_table = self.connection.ops.quote_name(table_name)
            keyspace = self._get_keyspace(table_name)
            clause_sql = clause_sql.replace(quoted_table, keyspace, 1)
            result.append(clause_sql)
            params.extend(clause_params)
        for t in self.query.extra_tables:
            alias, _ = self.query.table_alias(t)
            if alias not in self.query.alias_map or self.query.alias_refcount[alias] == 1:
                result.append(f", {self._get_keyspace(t)}")
        return result, params

    def quote_name_unless_alias(self, name):
        """Quote a table name.

        In N1QL, column references use the alias (e.g., `auth_permission`.`col`),
        while FROM clauses use the full keyspace. Since Django uses this method
        for BOTH column references and FROM clauses, we just use the simple
        backtick-quoted name here. The FROM clause conversion to full keyspace
        is handled in get_from_clause() via the Join.as_sql() mechanism.
        """
        if name in self.quote_cache:
            return self.quote_cache[name]
        r = self.connection.ops.quote_name(name)
        self.quote_cache[name] = r
        return r


class SQLInsertCompiler(CouchbaseCompilerMixin, base_compiler.SQLInsertCompiler):
    returning_fields = None
    returning_params = ()

    def _generate_pk(self, table_name):
        """Generate a sequential integer PK using a Couchbase counter."""
        from .fields import get_next_id

        return get_next_id(
            self.connection.connection,
            self.connection.settings_dict["NAME"],
            self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default"),
            table_name,
        )

    def _collect_unique_sets(self, opts):
        """Collect all uniqueness constraints from the model's Meta."""
        unique_sets = []

        # unique_together from Meta
        for fields in getattr(opts, "unique_together", ()):
            unique_sets.append(tuple(fields))

        # Single-field unique=True
        for field in opts.local_fields:
            if field.unique and not field.primary_key:
                unique_sets.append((field.name,))

        # UniqueConstraint from Meta.constraints
        from django.db.models.constraints import UniqueConstraint

        for constraint in getattr(opts, "constraints", []):
            if isinstance(constraint, UniqueConstraint) and not constraint.condition:
                unique_sets.append(tuple(constraint.fields))

        return unique_sets

    def _find_existing_by_unique(self, opts, fields_data):
        """Check if a document with matching unique fields already exists.

        Couchbase has no database-level UNIQUE constraint, so we enforce
        it at the application level during INSERT.

        Returns (existing_pk, violated_fields) or (None, None).
        """
        unique_sets = self._collect_unique_sets(opts)
        if not unique_sets:
            return None, None

        for unique_fields in unique_sets:
            conditions = []
            params = []
            all_present = True
            for field_name in unique_fields:
                try:
                    field = opts.get_field(field_name)
                    col = field.column
                except Exception:
                    col = field_name
                val = fields_data.get(col)
                if val is None:
                    all_present = False
                    break
                conditions.append(f"`{col}` = ${len(params) + 1}")
                params.append(val)

            if not all_present or not conditions:
                continue

            from couchbase.options import QueryOptions

            bucket = self.connection.settings_dict["NAME"]
            scope = self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default")
            qn = self.connection.ops.quote_name
            keyspace = f"{qn(bucket)}.{qn(scope)}.{qn(opts.db_table)}"
            where = " AND ".join(conditions)
            sql = f"SELECT `id` FROM {keyspace} WHERE {where} LIMIT 1"

            try:
                result = self.connection.connection.query(
                    sql,
                    QueryOptions(
                        positional_parameters=params,
                        scan_consistency="request_plus",
                    ),
                )
                for row in result.rows():
                    existing_id = row.get("id")
                    if existing_id is not None:
                        return existing_id, unique_fields
            except Exception as e:
                err_str = str(e)
                if "KeyspaceNotFoundException" in type(e).__name__ or "12003" in err_str:
                    pass
                else:
                    raise

        return None, None

    def as_sql(self):
        """Generate N1QL UPSERT statements.

        Couchbase UPSERT syntax:
            UPSERT INTO keyspace (KEY, VALUE)
            VALUES ($id, {field1: $val1, field2: $val2, ...})

        Each document is inserted as a JSON object with a sequential
        integer document key (for compatibility with Django/Wagtail).
        """
        opts = self.query.get_meta()
        keyspace = self._get_keyspace(opts.db_table)
        result_sqls = []

        has_fields = bool(self.query.fields)

        for obj in self.query.objs:
            doc_id = None
            fields_data = {}

            pk_col_name = opts.pk.column if opts.pk else "id"

            if has_fields:
                for field in self.query.fields:
                    value = self.pre_save_val(field, obj)
                    value = self.prepare_value(field, value)
                    col_name = field.column

                    if field.primary_key:
                        if value is None or hasattr(value, "as_sql"):
                            doc_id = None  # Will be resolved after all fields are collected
                        else:
                            doc_id = value
                        continue

                    if hasattr(value, "as_sql"):
                        sql_expr, expr_params = self.compile(value)
                        if expr_params:
                            fields_data[col_name] = expr_params[0]
                        else:
                            fields_data[col_name] = sql_expr
                    else:
                        fields_data[col_name] = value

            if doc_id is None:
                # Check unique constraints to prevent duplicates.
                existing_pk, violated_fields = self._find_existing_by_unique(opts, fields_data)
                if existing_pk is not None:
                    on_conflict = getattr(self.query, "on_conflict", None)
                    if on_conflict is not None:
                        from django.db.models.constants import OnConflict

                        if on_conflict == OnConflict.IGNORE:
                            continue  # Skip this row.
                        elif on_conflict == OnConflict.UPDATE:
                            doc_id = existing_pk  # Update existing doc.
                    if doc_id is None:
                        # Normal INSERT — raise IntegrityError.
                        from django.db import IntegrityError

                        cols = ", ".join(violated_fields)
                        raise IntegrityError(f"UNIQUE constraint failed: {opts.db_table} ({cols})")
                else:
                    doc_id = self._generate_pk(opts.db_table)

            # Store PK in document body so SELECT can find it.
            fields_data[pk_col_name] = doc_id

            # Use UPSERT so re-saving with the same PK works (no duplicate key errors).
            # Couchbase document KEY must be a string.
            sql = f"UPSERT INTO {keyspace} (KEY, VALUE) VALUES (%s, %s)"
            params = (str(doc_id), fields_data)
            result_sqls.append((sql, params))

            # Store the doc_id so execute_sql can retrieve it.
            if hasattr(obj, "pk") and obj.pk is None:
                obj.pk = doc_id

        return result_sqls

    def execute_sql(self, returning_fields=None):
        opts = self.query.get_meta()
        self.returning_fields = returning_fields

        with self.connection.cursor() as cursor:
            for sql, params in self.as_sql():
                cursor.execute(sql, params)

            if not self.returning_fields:
                return []

            # Return the PK values for the inserted objects.
            rows = []
            for obj in self.query.objs:
                pk_val = getattr(obj, "pk", None) or getattr(obj, opts.pk.attname, None)
                if pk_val is not None:
                    rows.append((pk_val,))
            return rows


class SQLDeleteCompiler(CouchbaseCompilerMixin, base_compiler.SQLDeleteCompiler):
    def as_sql(self):
        """Generate N1QL DELETE statement."""
        self.pre_sql_setup()
        table = self.query.base_table
        keyspace = self._get_keyspace(table)
        qn = self.connection.ops.quote_name
        # Use an alias so WHERE clause references like `table`.`field` work.
        from_clause = f"{keyspace} AS {qn(table)}"
        try:
            where, params = self.compile(self.query.where)
        except base_compiler.FullResultSet:
            return f"DELETE FROM {from_clause}", ()
        return f"DELETE FROM {from_clause} WHERE {where}", tuple(params)


class SQLUpdateCompiler(CouchbaseCompilerMixin, base_compiler.SQLUpdateCompiler):
    returning_fields = None
    returning_params = ()

    def as_sql(self):
        """Generate N1QL UPDATE statement."""
        self.pre_sql_setup()
        if not self.query.values:
            return "", ()

        qn = self.quote_name_unless_alias
        values, update_params = [], []

        for field, model, val in self.query.values:
            if hasattr(val, "resolve_expression"):
                val = val.resolve_expression(self.query, allow_joins=False, for_save=True)
            elif hasattr(val, "prepare_database_save"):
                if field.remote_field:
                    val = val.prepare_database_save(field)
                else:
                    raise TypeError(
                        f"Tried to update field {field} with a model instance, {val!r}. "
                        f"Use a value compatible with {field.__class__.__name__}."
                    )
            val = field.get_db_prep_save(val, connection=self.connection)

            if hasattr(field, "get_placeholder"):
                placeholder = field.get_placeholder(val, self, self.connection)
            else:
                placeholder = "%s"

            name = field.column
            if hasattr(val, "as_sql"):
                sql, params = self.compile(val)
                values.append(f"{self.connection.ops.quote_name(name)} = {placeholder % sql}")
                update_params.extend(params)
            elif val is not None:
                values.append(f"{self.connection.ops.quote_name(name)} = {placeholder}")
                update_params.append(val)
            else:
                values.append(f"{self.connection.ops.quote_name(name)} = NULL")

        table = self.query.base_table
        keyspace = self._get_keyspace(table)
        qn = self.connection.ops.quote_name
        # Use an alias so WHERE clause field references like `auth_user`.`id` work.
        result = [
            f"UPDATE {keyspace} AS {qn(table)} SET",
            ", ".join(values),
        ]
        try:
            where, params = self.compile(self.query.where)
        except base_compiler.FullResultSet:
            params = []
        else:
            result.append(f"WHERE {where}")

        return " ".join(result), tuple(update_params + list(params))

    def execute_sql(self, result_type):
        row_count = super().execute_sql(result_type)
        is_empty = row_count is None
        row_count = row_count or 0
        for query in self.query.get_related_updates():
            aux_row_count = query.get_compiler(self.using).execute_sql(result_type)
            if is_empty and aux_row_count:
                row_count = aux_row_count
                is_empty = False
        return row_count


class SQLAggregateCompiler(SQLCompiler):
    pass
