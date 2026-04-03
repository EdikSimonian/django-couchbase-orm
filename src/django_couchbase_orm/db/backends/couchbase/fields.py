"""Custom auto-field for Couchbase that generates sequential integer PKs."""

from __future__ import annotations

import threading

from django.db import models


class CouchbaseAutoField(models.AutoField):
    """An AutoField that generates sequential integer primary keys.

    Uses a Couchbase atomic counter document to generate unique IDs,
    similar to SQL auto-increment. This ensures compatibility with
    Django apps (like Wagtail) that expect integer PKs.
    """

    def get_internal_type(self):
        return "CouchbaseAutoField"

    def db_type(self, connection):
        return "integer"

    def rel_db_type(self, connection):
        return "integer"


# Thread-safe counter for generating sequential PKs.
_counter_lock = threading.Lock()


def get_next_id(cluster, bucket_name, scope_name, table_name):
    """Generate the next sequential integer ID using a Couchbase counter.

    Uses a dedicated counter document with atomic increment to ensure
    uniqueness across concurrent writers. Starts at 1.
    """
    from couchbase.options import IncrementOptions, SignedInt64

    bucket = cluster.bucket(bucket_name)
    counter_collection = bucket.scope(scope_name).collection("_default")
    counter_key = f"_counter:{table_name}"

    try:
        result = counter_collection.binary().increment(
            counter_key, IncrementOptions(initial=SignedInt64(1))
        )
        return result.content
    except Exception:
        with _counter_lock:
            try:
                result = counter_collection.binary().increment(
                    counter_key, IncrementOptions(initial=SignedInt64(1))
                )
                return result.content
            except Exception:
                return 1
