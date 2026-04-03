"""Custom auto-field for Couchbase that generates UUID primary keys."""

from __future__ import annotations

import uuid

from django.db import models


class CouchbaseAutoField(models.AutoField):
    """An AutoField that generates UUID strings instead of integers.

    Couchbase uses string document keys, not auto-incrementing integers.
    This field generates UUIDs when no value is specified.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("primary_key", True)
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

    def get_internal_type(self):
        return "CouchbaseAutoField"

    def db_type(self, connection):
        return "varchar(36)"

    def rel_db_type(self, connection):
        return "varchar(36)"

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return str(uuid.uuid4())
        return str(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        return str(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return str(value)

    def to_python(self, value):
        if value is None:
            return None
        return str(value)

    def formfield(self, **kwargs):
        return None

    def validate(self, value, model_instance):
        pass

    def get_db_converters(self, connection):
        return []
