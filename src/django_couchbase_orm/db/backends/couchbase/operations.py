"""Couchbase database operations — backend-specific SQL/N1QL generation."""

from __future__ import annotations

import datetime

from django.db.backends.base.operations import BaseDatabaseOperations
from django.utils import timezone


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "django_couchbase_orm.db.backends.couchbase.compiler"

    # CouchbaseAutoField uses UUIDs (strings), not integers.
    # Add it to the range map so Django's system checks don't fail.
    integer_field_ranges = {
        **BaseDatabaseOperations.integer_field_ranges,
        "CouchbaseAutoField": (-9223372036854775808, 9223372036854775807),
    }

    # N1QL uses backtick quoting.
    def quote_name(self, name):
        if name.startswith("`") and name.endswith("`"):
            return name
        name = name.replace("`", "``")
        return f"`{name}`"

    def no_limit_value(self):
        # N1QL doesn't require a limit; return a large value when Django needs one.
        return None

    def max_name_length(self):
        # Couchbase has no practical name length limit.
        return None

    def pk_default_value(self):
        return "NULL"

    def last_insert_id(self, cursor, table_name, pk_name):
        return cursor.lastrowid

    def bulk_insert_sql(self, fields, placeholder_rows):
        # Return the VALUES clause for multi-row INSERT.
        return "VALUES " + ", ".join("({})".format(", ".join(row)) for row in placeholder_rows)

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
        # Store timezone-aware datetimes in UTC with offset suffix.
        if timezone.is_aware(value):
            value = value.astimezone(datetime.timezone.utc)
        else:
            # Naive datetime with USE_TZ=True: assume UTC (matches Django convention).
            from django.conf import settings

            if getattr(settings, "USE_TZ", False):
                value = value.replace(tzinfo=datetime.timezone.utc)
        return value.isoformat()

    def adapt_timefield_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    def adapt_decimalfield_value(self, value, max_digits=None, decimal_places=None):
        """Serialize a Decimal as a JSON string to preserve precision.

        JSON only has float (IEEE 754) — converting Decimal to float would lose
        precision for large or high-scale values. We round-trip through str so
        the exact decimal representation survives. The DecimalField converter
        on the way back rebuilds Decimal from this string.
        """
        if value is None:
            return None
        from decimal import Decimal

        if isinstance(value, Decimal):
            return str(value)
        # Already-str values pass through unchanged.
        if isinstance(value, str):
            return value
        return str(Decimal(str(value)))

    # --- SQL generation helpers ---

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        """Return a list of N1QL statements to delete all data from the given tables."""
        if not tables:
            return []
        from django_couchbase_orm.query.n1ql import (
            _validate_bucket,
            _validate_scope_or_collection,
        )

        sql_list = []
        bucket = _validate_bucket(self.connection.settings_dict["NAME"])
        scope = _validate_scope_or_collection(self.connection.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default"))
        for table in tables:
            table = _validate_scope_or_collection(table)
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

    def convert_datefield_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, str):
            from django.utils.dateparse import parse_date

            return parse_date(value)
        return value

    def convert_datetimefield_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, str):
            from django.utils.dateparse import parse_datetime

            dt = parse_datetime(value)
            if dt is not None:
                return self._ensure_tz_aware(dt)
            return dt
        if isinstance(value, datetime.datetime):
            return self._ensure_tz_aware(value)
        return value

    def _ensure_tz_aware(self, dt):
        """Make a datetime timezone-aware (UTC) when USE_TZ=True."""
        from django.conf import settings

        if getattr(settings, "USE_TZ", False) and timezone.is_naive(dt):
            return timezone.make_aware(dt, datetime.timezone.utc)
        return dt

    def convert_timefield_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, str):
            from django.utils.dateparse import parse_time

            return parse_time(value)
        return value

    def convert_integerfield_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, list):
            return None if len(value) == 0 else value[0] if len(value) == 1 else value
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == "DateField":
            converters.append(self.convert_datefield_value)
        elif internal_type == "DateTimeField":
            converters.append(self.convert_datetimefield_value)
        elif internal_type == "TimeField":
            converters.append(self.convert_timefield_value)
        elif internal_type == "DecimalField":
            converters.append(self.convert_decimalfield_value)
        elif internal_type in (
            "IntegerField",
            "BigIntegerField",
            "SmallIntegerField",
            "PositiveIntegerField",
            "PositiveBigIntegerField",
            "PositiveSmallIntegerField",
            "AutoField",
            "BigAutoField",
            "SmallAutoField",
            "CouchbaseAutoField",
        ):
            converters.append(self.convert_integerfield_value)
        return converters

    def convert_decimalfield_value(self, value, expression, connection):
        """Decode the string representation persisted by adapt_decimalfield_value."""
        if value is None:
            return None
        from decimal import Decimal

        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return value

    def combine_expression(self, connector, sub_expressions):
        if connector == "||":
            return " || ".join(sub_expressions)
        return super().combine_expression(connector, sub_expressions)
