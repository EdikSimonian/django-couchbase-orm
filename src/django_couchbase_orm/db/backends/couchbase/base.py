"""Couchbase database backend for Django."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.db.backends.base.base import BaseDatabaseWrapper

from .client import DatabaseClient
from .creation import DatabaseCreation
from .cursor import CouchbaseCursor
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

_autofield_patched = False


def _patch_autofields():
    """Patch Django's AutoField classes to use UUID strings instead of integers.

    Couchbase uses string document keys, so AutoField must produce/accept strings.
    This is called once when the connection is initialized.
    """
    global _autofield_patched
    if _autofield_patched:
        return
    _autofield_patched = True

    from django.db.models import fields as model_fields

    for field_cls_name in ("AutoField", "BigAutoField", "SmallAutoField"):
        field_cls = getattr(model_fields, field_cls_name)

        def _make_patched(original_cls):
            original_get_prep = original_cls.get_prep_value
            original_get_db_prep = original_cls.get_db_prep_value
            original_to_python = original_cls.to_python

            def get_prep_value(self, value):
                if value is None:
                    return str(uuid.uuid4())
                return str(value)

            def get_db_prep_value(self, value, connection, prepared=False):
                if value is None:
                    return str(uuid.uuid4())
                return str(value)

            def to_python(self, value):
                if value is None:
                    return value
                return str(value)

            original_cls.get_prep_value = get_prep_value
            original_cls.get_db_prep_value = get_db_prep_value
            original_cls.to_python = to_python

        _make_patched(field_cls)


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
    pattern_esc = (
        r"REPLACE(REPLACE(REPLACE({}, '\', '\\'), '%%', '\%%'), '_', '\_')"
    )
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

    def get_connection_params(self):
        settings = self.settings_dict
        return {
            "connection_string": settings.get("HOST", "couchbase://localhost"),
            "username": settings.get("USER", "Administrator"),
            "password": settings.get("PASSWORD", "password"),
            "bucket": settings.get("NAME", "default"),
            "scope": settings.get("OPTIONS", {}).get("SCOPE", "_default"),
        }

    def get_new_connection(self, conn_params):
        from couchbase.auth import PasswordAuthenticator
        from couchbase.cluster import Cluster
        from couchbase.options import ClusterOptions, ClusterTimeoutOptions

        authenticator = PasswordAuthenticator(
            conn_params["username"], conn_params["password"]
        )

        timeout_config = self.settings_dict.get("OPTIONS", {}).get(
            "timeout_options", {}
        )
        timeout_kwargs = {}
        if "kv_timeout" in timeout_config:
            timeout_kwargs["kv_timeout"] = timedelta(
                seconds=timeout_config["kv_timeout"]
            )
        if "query_timeout" in timeout_config:
            timeout_kwargs["query_timeout"] = timedelta(
                seconds=timeout_config["query_timeout"]
            )

        cluster_opts = ClusterOptions(
            authenticator,
            timeout_options=(
                ClusterTimeoutOptions(**timeout_kwargs) if timeout_kwargs else None
            ),
        )

        conn_string = conn_params["connection_string"]
        if conn_string.startswith("couchbases://"):
            cluster_opts.apply_profile("wan_development")

        cluster = Cluster.connect(conn_string, cluster_opts)

        wait_timeout = self.settings_dict.get("OPTIONS", {}).get(
            "wait_until_ready_timeout", 20
        )
        cluster.wait_until_ready(timedelta(seconds=wait_timeout))

        self._cluster = cluster
        self._bucket = cluster.bucket(conn_params["bucket"])

        return cluster

    def create_cursor(self, name=None):
        params = self.get_connection_params()
        return CouchbaseCursor(
            self.connection,
            params["bucket"],
            params["scope"],
        )

    def init_connection_state(self):
        """Patch AutoField to work with string UUIDs instead of integers."""
        _patch_autofields()

    def _set_autocommit(self, autocommit):
        # Couchbase doesn't have traditional autocommit mode.
        pass

    def _commit(self):
        # No-op: transactions not yet supported.
        pass

    def _rollback(self):
        # No-op: transactions not yet supported.
        pass

    def _close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.connection = None
        self._cluster = None
        self._bucket = None

    def is_usable(self):
        try:
            self.connection.ping()
            return True
        except Exception:
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
