"""Couchbase database backend for Django."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.backends.base.base import BaseDatabaseWrapper

from .client import DatabaseClient
from .creation import DatabaseCreation
from .cursor import CouchbaseCursor
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

logger = logging.getLogger("django.db.backends.couchbase")

_autofield_patched = False


def _patch_autofields():
    """Patch Django's AutoField classes to accept string-typed integer values.

    Couchbase stores all values as JSON, so integer PKs come back as
    strings or ints depending on how they were stored. The AutoField
    must tolerate both without raising ValueError.
    """
    global _autofield_patched
    if _autofield_patched:
        return
    _autofield_patched = True

    from django.db.models import fields as model_fields

    for field_cls_name in ("AutoField", "BigAutoField", "SmallAutoField"):
        field_cls = getattr(model_fields, field_cls_name)

        def _make_patched(original_cls):
            def get_prep_value(self, value):
                if value is None or value == "":
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"Field expected a number but got {value!r}.")

            def get_db_prep_value(self, value, connection, prepared=False):
                if value is None or value == "":
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"Field expected a number but got {value!r}.")

            def to_python(self, value):
                if value is None or value == "":
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError):
                    raise ValueError(f"Field expected a number but got {value!r}.")

            original_cls.get_prep_value = get_prep_value
            original_cls.get_db_prep_value = get_db_prep_value
            original_cls.to_python = to_python

        _make_patched(field_cls)


_sql_functions_patched = False


def _patch_sql_functions():
    """Register as_couchbase methods on Django SQL functions.

    N1QL uses different function names than SQL:
    - SUBSTRING → SUBSTR
    - LENGTH stays LENGTH (same)
    - CONCAT stays CONCAT (same)
    """
    global _sql_functions_patched
    if _sql_functions_patched:
        return
    _sql_functions_patched = True

    from django.db.models import Value
    from django.db.models.functions import Substr

    def substr_as_couchbase(self, compiler, connection, **extra_context):
        # N1QL SUBSTR is 0-indexed, SQL SUBSTRING is 1-indexed.
        # Subtract 1 from the position argument to convert.
        clone = self.copy()
        pos_expr = clone.source_expressions[1]
        clone.source_expressions[1] = pos_expr - Value(1)
        return clone.as_sql(compiler, connection, function="SUBSTR", **extra_context)

    Substr.as_couchbase = substr_as_couchbase


class _CouchbaseDatabase:
    """Minimal DB-API 2.0 module stand-in for Django's error wrapping."""

    class Error(Exception):
        pass

    class DatabaseError(Error):
        pass

    class InterfaceError(Error):
        pass

    class DataError(DatabaseError):
        pass

    class OperationalError(DatabaseError):
        pass

    class IntegrityError(DatabaseError):
        pass

    class InternalError(DatabaseError):
        pass

    class ProgrammingError(DatabaseError):
        pass

    class NotSupportedError(DatabaseError):
        pass


_cached_clusters: dict[str, tuple] = {}  # cache_key -> (cluster, bucket)


def reset_cached_clusters():
    """Clear the module-level cluster cache.

    Call this when recycling workers (e.g., Gunicorn pre_fork) or in tests.
    Does NOT close SDK connections (to avoid segfault) — they will be
    garbage collected when the process exits.
    """
    _cached_clusters.clear()


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "couchbase"
    display_name = "Couchbase"
    Database = _CouchbaseDatabase

    # Couchbase stores JSON documents — types are informational for schema editor.
    data_types = {
        "AutoField": "varchar",
        "BigAutoField": "varchar",
        "SmallAutoField": "varchar",
        "CouchbaseAutoField": "varchar(36)",
        "BinaryField": "text",
        "BooleanField": "boolean",
        "CharField": "varchar(%(max_length)s)",
        "DateField": "varchar",
        "DateTimeField": "varchar",
        "DecimalField": "number",
        "DurationField": "varchar",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "number",
        "IntegerField": "integer",
        "BigIntegerField": "integer",
        "IPAddressField": "varchar(15)",
        "GenericIPAddressField": "varchar(39)",
        "JSONField": "json",
        "PositiveBigIntegerField": "integer",
        "PositiveIntegerField": "integer",
        "PositiveSmallIntegerField": "integer",
        "SlugField": "varchar(%(max_length)s)",
        "SmallIntegerField": "integer",
        "TextField": "text",
        "TimeField": "varchar",
        "UUIDField": "varchar(36)",
    }

    # N1QL operators for Django lookups.
    # Case-insensitive lookups use LOWER() on the value side.
    # The column side is wrapped via lookup_cast() in operations.py.
    operators = {
        "exact": "= %s",
        "iexact": "= LOWER(%s)",
        "contains": "LIKE %s",
        "icontains": "LIKE LOWER(%s)",
        "regex": "REGEXP_CONTAINS(%s)",
        "iregex": "REGEXP_CONTAINS(%s)",
        "gt": "> %s",
        "gte": ">= %s",
        "lt": "< %s",
        "lte": "<= %s",
        "startswith": "LIKE %s",
        "endswith": "LIKE %s",
        "istartswith": "LIKE LOWER(%s)",
        "iendswith": "LIKE LOWER(%s)",
    }

    # N1QL pattern operations for non-string RHS.
    pattern_esc = r"REPLACE(REPLACE(REPLACE({}, '\', '\\'), '%%', '\%%'), '_', '\_')"
    pattern_ops = {
        "contains": r"LIKE '%%' || {} || '%%'",
        "icontains": r"LIKE '%%' || LOWER({}) || '%%'",
        "startswith": r"LIKE {} || '%%'",
        "istartswith": r"LIKE LOWER({}) || '%%'",
        "endswith": r"LIKE '%%' || {}",
        "iendswith": r"LIKE '%%' || LOWER({})",
    }

    SchemaEditorClass = DatabaseSchemaEditor
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations

    def __init__(self, settings_dict, alias="default"):
        # Ensure required keys have defaults for Django's connection machinery.
        if "CONN_MAX_AGE" not in settings_dict:
            settings_dict["CONN_MAX_AGE"] = None
        if "CONN_HEALTH_CHECKS" not in settings_dict:
            settings_dict["CONN_HEALTH_CHECKS"] = False
        if "AUTOCOMMIT" not in settings_dict:
            settings_dict["AUTOCOMMIT"] = True
        if "TIME_ZONE" not in settings_dict:
            settings_dict["TIME_ZONE"] = None
        if "OPTIONS" not in settings_dict:
            settings_dict["OPTIONS"] = {}

        super().__init__(settings_dict, alias)

        # Cache for the Couchbase cluster/bucket objects.
        self._cluster = None
        self._bucket = None
        # Active N1QL transaction ID (set by BEGIN WORK, cleared by COMMIT/ROLLBACK).
        self._txid: str | None = None

    def get_connection_params(self):
        settings = self.settings_dict
        return {
            "connection_string": settings.get("HOST", "couchbase://localhost"),
            "username": settings.get("USER", "Administrator"),
            "password": settings.get("PASSWORD", ""),
            "bucket": settings.get("NAME", "default"),
            "scope": settings.get("OPTIONS", {}).get("SCOPE", "_default"),
        }

    def get_new_connection(self, conn_params):
        # Reuse existing cluster/bucket from module-level cache to avoid the
        # Couchbase SDK segfault that occurs when opening a new bucket while
        # a previous cluster's background threads are still running.
        cache_key = str(conn_params.get("connection_string", "")) + ":" + str(conn_params.get("bucket", ""))
        if cache_key in _cached_clusters:
            cluster, bucket = _cached_clusters[cache_key]
            self._cluster = cluster
            self._bucket = bucket
            return cluster

        from couchbase.auth import PasswordAuthenticator
        from couchbase.cluster import Cluster
        from couchbase.options import ClusterOptions, ClusterTimeoutOptions

        authenticator = PasswordAuthenticator(conn_params["username"], conn_params["password"])

        timeout_config = self.settings_dict.get("OPTIONS", {}).get("timeout_options", {})
        timeout_kwargs = {}
        if "kv_timeout" in timeout_config:
            timeout_kwargs["kv_timeout"] = timedelta(seconds=timeout_config["kv_timeout"])
        if "query_timeout" in timeout_config:
            timeout_kwargs["query_timeout"] = timedelta(seconds=timeout_config["query_timeout"])

        cluster_kwargs = {
            "timeout_options": ClusterTimeoutOptions(**timeout_kwargs) if timeout_kwargs else None,
        }
        # OpenTelemetry tracing support (SDK 4.6+).
        tracer = self.settings_dict.get("OPTIONS", {}).get("TRACER")
        if tracer is not None:
            cluster_kwargs["tracer"] = tracer

        cluster_opts = ClusterOptions(authenticator, **cluster_kwargs)

        conn_string = conn_params["connection_string"]
        if conn_string.startswith("couchbases://"):
            cluster_opts.apply_profile("wan_development")

        cluster = Cluster.connect(conn_string, cluster_opts)

        wait_timeout = self.settings_dict.get("OPTIONS", {}).get("wait_until_ready_timeout", 20)
        cluster.wait_until_ready(timedelta(seconds=wait_timeout))

        self._cluster = cluster
        self._bucket = cluster.bucket(conn_params["bucket"])
        _cached_clusters[cache_key] = (self._cluster, self._bucket)

        return cluster

    def create_cursor(self, name=None):
        params = self.get_connection_params()
        options = self.settings_dict.get("OPTIONS", {})
        scan_consistency = options.get("SCAN_CONSISTENCY", "request_plus")
        # adhoc=False enables prepared statement caching (server-side query plan reuse).
        adhoc = options.get("ADHOC", True)
        graceful = bool(options.get("GRACEFUL_QUERY_ERRORS", False))
        return CouchbaseCursor(
            self.connection,
            params["bucket"],
            params["scope"],
            scan_consistency=scan_consistency,
            adhoc=adhoc,
            wrapper=self,
            graceful_query_errors=graceful,
        )

    def init_connection_state(self):
        """Patch AutoField, SQL functions, and bridge connection pools."""
        _patch_autofields()
        _patch_sql_functions()

        # Auto-generate settings.COUCHBASE from DATABASES if not configured,
        # and share this connection with the Document API.
        from django_couchbase_orm.connection import (
            get_or_create_couchbase_settings,
            share_backend_connection,
        )

        get_or_create_couchbase_settings()
        share_backend_connection(self.alias)

    def _set_autocommit(self, autocommit):
        # Couchbase is always in autocommit for individual ops.
        pass

    def _get_durability_level(self):
        """Get the configured durability level for transactions.

        Returns the DURABILITY_LEVEL from DATABASES OPTIONS.
        Default is "none" which works on single-node and multi-node clusters.
        Production multi-node clusters should set "majority" for full ACID durability.
        """
        return self.settings_dict.get("OPTIONS", {}).get("DURABILITY_LEVEL", "none")

    def _transactions_mode(self):
        """Return the configured transaction mode: 'enabled' or 'disabled'.

        Default is 'enabled'. Set OPTIONS["TRANSACTIONS"]="disabled" to opt
        out (atomic() becomes a true no-op) on clusters where BEGIN WORK is
        not supported.
        """
        return self.settings_dict.get("OPTIONS", {}).get("TRANSACTIONS", "enabled").lower()

    def _start_transaction_under_autocommit(self):
        """Start a N1QL transaction via BEGIN WORK.

        Raises DatabaseError on failure rather than silently autocommitting,
        so callers cannot mistake a failed BEGIN for a successful transaction.
        Set OPTIONS["TRANSACTIONS"]="disabled" to skip the BEGIN entirely.
        """
        from couchbase.options import QueryOptions

        if self._transactions_mode() == "disabled":
            self._txid = None
            return

        self.ensure_connection()
        durability = self._get_durability_level()
        try:
            result = self._cluster.query(
                "BEGIN WORK",
                QueryOptions(raw={"durability_level": durability}),
            )
            rows = list(result.rows())
            self._txid = rows[0]["txid"]
        except Exception as e:
            self._txid = None
            err_msg = str(e)
            if "DurabilityImpossible" in err_msg or "durability_impossible" in err_msg:
                raise _CouchbaseDatabase.OperationalError(
                    f"Transaction BEGIN failed: durability level '{durability}' "
                    f"requires replica nodes. For a single-node cluster, set "
                    f"DURABILITY_LEVEL='none' in DATABASES OPTIONS, or set "
                    f"OPTIONS['TRANSACTIONS']='disabled' to skip transactional wrapping."
                ) from e
            raise _CouchbaseDatabase.OperationalError(
                f"Transaction BEGIN failed: {e}. Set OPTIONS['TRANSACTIONS']='disabled' to skip transactions."
            ) from e

    def _commit(self):
        if self._txid is None:
            return
        from couchbase.options import QueryOptions

        txid = self._txid
        self._txid = None
        try:
            durability = self._get_durability_level()
            self._cluster.query(
                "COMMIT WORK",
                QueryOptions(raw={"txid": txid, "durability_level": durability}),
            ).execute()
        except Exception as e:
            err_msg = str(e)
            if "DurabilityImpossible" in err_msg or "durability_impossible" in err_msg:
                raise _CouchbaseDatabase.OperationalError(
                    f"Transaction COMMIT failed: durability level '{self._get_durability_level()}' "
                    f"requires replica nodes. Set DURABILITY_LEVEL='none' in DATABASES OPTIONS "
                    f"for single-node clusters."
                ) from e
            raise

    def _rollback(self):
        if self._txid is None:
            return
        from couchbase.options import QueryOptions

        txid = self._txid
        self._txid = None
        try:
            self._cluster.query(
                "ROLLBACK WORK",
                QueryOptions(raw={"txid": txid}),
            ).execute()
        except Exception as e:
            # Rollback failures are logged but not raised — the transaction
            # will expire and auto-rollback on the server side.
            logger.debug("Transaction ROLLBACK failed (will auto-expire): %s", e)

    def close(self):
        """Override close() to keep the Couchbase cluster alive.

        The Couchbase SDK's C++ layer segfaults if cluster.close() is called
        while background threads (logging_meter, threshold_logging) are still
        running, or if a new cluster.bucket() call is made before the old
        cluster's threads have fully stopped. This is a known SDK issue on
        macOS and can occur on Linux under load.

        Instead of closing, we keep the cluster connection alive in
        _cached_clusters and reuse it on the next ensure_connection(). The
        cluster is only released when the Python process exits (via GC).

        For Gunicorn/uWSGI worker recycling, call reset_cached_clusters()
        in the pre_fork or post_fork hook.
        """
        self.run_on_commit = []
        self.needs_rollback = False

    def _close(self):
        pass

    def ensure_connection(self):
        """Override to reuse existing cluster — avoids SDK segfault on reconnect."""
        if self.connection is not None:
            return
        if self._cluster is not None and self._bucket is not None:
            self.connection = self._cluster
            return
        super().ensure_connection()

    def connect(self):
        """Override connect() to reuse existing cluster connection."""
        if self._cluster is not None and self._bucket is not None:
            self.connection = self._cluster
            self.init_connection_state()
            return
        super().connect()

    def is_usable(self):
        try:
            if self.connection is None:
                return False
            self.connection.ping()
            return True
        except Exception as e:
            logger.debug("Connection not usable: %s", e)
            return False

    def get_database_version(self):
        # Return a version tuple. Couchbase version can be queried from cluster
        # manager, but for now use a default.
        return (7, 6, 0)

    @property
    def couchbase_bucket(self):
        """Access the Couchbase Bucket object."""
        self.ensure_connection()
        return self._bucket

    @property
    def couchbase_scope(self):
        """Access the Couchbase Scope object."""
        scope_name = self.settings_dict.get("OPTIONS", {}).get("SCOPE", "_default")
        return self._bucket.scope(scope_name)

    @property
    def couchbase_cluster(self):
        """Access the Couchbase Cluster object."""
        self.ensure_connection()
        return self._cluster

    def schema_editor(self, *args, **kwargs):
        return self.SchemaEditorClass(self, *args, **kwargs)
