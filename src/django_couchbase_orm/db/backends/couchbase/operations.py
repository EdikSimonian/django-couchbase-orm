"""Couchbase database operations — backend-specific SQL/N1QL generation."""

from __future__ import annotations

import datetime
import uuid

from django.db.backends.base.operations import BaseDatabaseOperations
from django.utils import timezone


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "django_couchbase_orm.db.backends.couchbase.compiler"

    # N1QL uses backtick quoting.
    def quote_name(self, name):
        if name.startswith("`") and name.endswith("`"):
            return name
        return f"`{name}`"

    def no_limit_value(self):
        # N1QL doesn't require a limit; return a large value when Django needs one.
        return None

    def max_name_length(self):
        # Couchbase has no practical name length limit.
        return None

    def pk_default_value(self):
        # Generate a UUID for new documents.
        return f"'{uuid.uuid4()}'"

    def last_insert_id(self, cursor, table_name, pk_name):
        return cursor.lastrowid

    def bulk_insert_sql(self, fields, placeholder_rows):
        # Return the VALUES clause for multi-row INSERT.
        return "VALUES " + ", ".join(
            "(%s)" % ", ".join(row) for row in placeholder_rows
        )

    # --- Date/time operations using N1QL date functions ---

    def date_extract_sql(self, lookup_type, sql, params):
        lookup_map = {
            "year": "DATE_PART_STR(%s, 'year')",
            "month": "DATE_PART_STR(%s, 'month')",
            "day": "DATE_PART_STR(%s, 'day')",
            "week_day": "(DATE_PART_STR(%s, 'dow') + 1)",
            "iso_week_day": "DATE_PART_STR(%s, 'dow')",
            "week": "DATE_PART_STR(%s, 'iso_week')",
            "iso_year": "DATE_PART_STR(%s, 'iso_year')",
            "quarter": "DATE_PART_STR(%s, 'quarter')",
        }
        if lookup_type in lookup_map:
            return lookup_map[lookup_type] % sql, params
        return f"DATE_PART_STR({sql}, '{lookup_type}')", params

    def date_trunc_sql(self, lookup_type, sql, params, tzname=None):
        lookup_map = {
            "year": "DATE_TRUNC_STR(%s, 'year')",
            "quarter": "DATE_TRUNC_STR(%s, 'quarter')",
            "month": "DATE_TRUNC_STR(%s, 'month')",
            "week": "DATE_TRUNC_STR(%s, 'iso_week')",
            "day": "DATE_TRUNC_STR(%s, 'day')",
        }
        if lookup_type in lookup_map:
            return lookup_map[lookup_type] % sql, params
        return f"DATE_TRUNC_STR({sql}, '{lookup_type}')", params

    def datetime_extract_sql(self, lookup_type, sql, params, tzname):
        return self.date_extract_sql(lookup_type, sql, params)

    def datetime_trunc_sql(self, lookup_type, sql, params, tzname):
        lookup_map = {
            "year": "DATE_TRUNC_STR(%s, 'year')",
            "quarter": "DATE_TRUNC_STR(%s, 'quarter')",
            "month": "DATE_TRUNC_STR(%s, 'month')",
            "week": "DATE_TRUNC_STR(%s, 'iso_week')",
            "day": "DATE_TRUNC_STR(%s, 'day')",
            "hour": "DATE_TRUNC_STR(%s, 'hour')",
            "minute": "DATE_TRUNC_STR(%s, 'minute')",
            "second": "DATE_TRUNC_STR(%s, 'second')",
        }
        if lookup_type in lookup_map:
            return lookup_map[lookup_type] % sql, params
        return f"DATE_TRUNC_STR({sql}, '{lookup_type}')", params

    def datetime_cast_date_sql(self, sql, params, tzname):
        return f"DATE_TRUNC_STR({sql}, 'day')", params

    def datetime_cast_time_sql(self, sql, params, tzname):
        return (
            f"SUBSTR(DATE_FORMAT_STR({sql}, '1111-11-11T00:00:00'), 11)",
            params,
        )

    def time_trunc_sql(self, lookup_type, sql, params, tzname=None):
        return f"DATE_TRUNC_STR({sql}, '{lookup_type}')", params

    def time_extract_sql(self, lookup_type, sql, params):
        lookup_map = {
            "hour": "DATE_PART_STR(%s, 'hour')",
            "minute": "DATE_PART_STR(%s, 'minute')",
            "second": "DATE_PART_STR(%s, 'second')",
        }
        if lookup_type in lookup_map:
            return lookup_map[lookup_type] % sql, params
        return f"DATE_PART_STR({sql}, '{lookup_type}')", params

    # --- Value adaptation ---

    def adapt_datefield_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    def adapt_datetimefield_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if timezone.is_aware(value):
            value = timezone.make_naive(value, datetime.timezone.utc)
        return value.isoformat()

    def adapt_timefield_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        if value is None:
            return None
        return float(value)

    # --- SQL generation helpers ---

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        """Return a list of N1QL statements to delete all data from the given tables."""
        if not tables:
            return []
        sql_list = []
        bucket = self.connection.settings_dict["NAME"]
        scope = self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default")
        for table in tables:
            keyspace = f"`{bucket}`.`{scope}`.`{table}`"
            sql_list.append(f"DELETE FROM {keyspace}")
        return sql_list

    def regex_lookup(self, lookup_type):
        if lookup_type == "regex":
            return "REGEXP_CONTAINS(%s, %s)"
        elif lookup_type == "iregex":
            return "REGEXP_CONTAINS(%s, '(?i)' || %s)"
        raise NotImplementedError(f"Unsupported regex lookup: {lookup_type}")

    def last_executed_query(self, cursor, sql, params):
        if params:
            return sql % tuple(repr(p) for p in params)
        return sql

    def lookup_cast(self, lookup_type, internal_type=None):
        # N1QL LIKE is case-sensitive, so wrap the LHS with LOWER for
        # case-insensitive lookups.
        if lookup_type in ("iexact", "icontains", "istartswith", "iendswith"):
            return "LOWER(%s)"
        return "%s"

    def format_for_duration_arithmetic(self, sql):
        return f"STR_TO_DURATION({sql} || 'ms')"

    def prep_for_iexact_query(self, x):
        """iexact uses = not LIKE, so don't escape LIKE special chars."""
        return str(x)

    def adapt_integerfield_value(self, value, internal_type=None):
        # Couchbase uses string document keys. When an AutoField stores a UUID
        # string, don't try to convert it to int.
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value

    def combine_expression(self, connector, sub_expressions):
        if connector == "||":
            return " || ".join(sub_expressions)
        return super().combine_expression(connector, sub_expressions)
