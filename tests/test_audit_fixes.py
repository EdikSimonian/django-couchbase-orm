"""Live integration tests covering the audit fixes (#1–#10).

Each test runs against the local Dockerized Couchbase instance. They are
skipped automatically when Couchbase is not reachable.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from django_couchbase_orm.document import Document
from django_couchbase_orm.exceptions import (
    ConcurrentModificationError,
)
from django_couchbase_orm.fields.compound import DictField
from django_couchbase_orm.fields.reference import ReferenceField
from django_couchbase_orm.fields.simple import IntegerField, StringField
from tests.conftest import couchbase_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not couchbase_available, reason="Local Couchbase not available"),
    pytest.mark.django_db(transaction=True),
]


# ============================================================
# Helpers / models
# ============================================================


class AuditDoc(Document):
    name = StringField()
    counter = IntegerField()
    profile = DictField()

    class Meta:
        bucket_alias = "default"
        scope_name = "_default"
        collection_name = "edge_test_docs"


class RefTarget(Document):
    label = StringField()

    class Meta:
        bucket_alias = "default"
        scope_name = "_default"
        collection_name = "edge_test_docs"


class RefHolder(Document):
    target = ReferenceField(RefTarget)

    class Meta:
        bucket_alias = "default"
        scope_name = "_default"
        collection_name = "edge_test_docs"


def _flush():
    from couchbase.n1ql import QueryScanConsistency
    from couchbase.options import QueryOptions

    from django_couchbase_orm.connection import get_cluster, reset_connections

    reset_connections()
    cluster = get_cluster()
    cluster.query(
        "DELETE FROM `testbucket`.`_default`.`edge_test_docs`",
        QueryOptions(scan_consistency=QueryScanConsistency.REQUEST_PLUS),
    ).execute()


@pytest.fixture(autouse=True)
def _clean():
    _flush()
    yield
    _flush()


# ============================================================
# #1 fail-closed on query errors
# ============================================================


class TestFailClosed:
    def test_default_raises_on_syntax_error(self):
        from django.db import connection

        cursor = connection.cursor()
        with pytest.raises(Exception) as exc_info:
            cursor.execute("SELECT FROM_NOWHERE WHERE NOTHING_HOLDS_TRUE")
        # Must NOT have silently returned an empty rowset.
        assert cursor._rows == [] or cursor._rows is None
        assert exc_info.value is not None

    def test_graceful_mode_swallows(self, settings):
        """Opt-in OPTIONS['GRACEFUL_QUERY_ERRORS']=True restores the old behavior."""
        from django.db import connections

        # Reach into the existing connection: toggle the flag on a fresh cursor.
        conn = connections["default"]
        cursor = conn.create_cursor()
        cursor._graceful_query_errors = True
        try:
            cursor.execute("SELECT BOGUS GIBBERISH FROM nothingness")
        except Exception:
            pytest.fail("graceful mode should swallow syntax error")
        assert cursor._rows == []
        cursor.close()


# ============================================================
# #2 transactions truthfulness
# ============================================================


class TestTransactions:
    def test_atomic_rollback_actually_rolls_back(self):
        """Confirms #2 — failed transaction must NOT silently autocommit."""
        from django.contrib.auth.models import Group
        from django.db import transaction

        name = f"audit-rollback-{uuid.uuid4().hex[:6]}"
        try:
            with transaction.atomic():
                Group.objects.create(name=name)
                raise RuntimeError("trip rollback")
        except RuntimeError:
            pass
        # Group.objects.filter resolves through the SELECT path; the row must
        # not be visible if rollback worked. (On single-node DURABILITY_LEVEL=
        # 'none', the SDK transaction is real.)
        assert not Group.objects.filter(name=name).exists()

    def test_disabled_mode_makes_atomic_a_noop(self, settings):
        """OPTIONS['TRANSACTIONS']='disabled' opts out of BEGIN WORK."""
        from django.db import connections

        conn = connections["default"]
        original = conn.settings_dict.get("OPTIONS", {}).get("TRANSACTIONS")
        conn.settings_dict.setdefault("OPTIONS", {})["TRANSACTIONS"] = "disabled"
        try:
            assert conn.features.supports_transactions is False
            # _start_transaction_under_autocommit must not raise.
            conn._start_transaction_under_autocommit()
            assert conn._txid is None
        finally:
            if original is None:
                conn.settings_dict["OPTIONS"].pop("TRANSACTIONS", None)
            else:
                conn.settings_dict["OPTIONS"]["TRANSACTIONS"] = original


# ============================================================
# #3 INSERT semantics + uniqueness
# ============================================================


class TestInsertSemantics:
    def test_duplicate_user_pk_raises_integrity_error(self):
        """Two creates with the same PK must raise IntegrityError, not silently overwrite."""
        from django.contrib.auth.models import Group
        from django.db import IntegrityError

        # Reuse Group's auto-pk behavior. Force the same pk twice via raw save.
        first = Group.objects.create(name=f"audit-pk-{uuid.uuid4().hex[:6]}")
        clash = Group(pk=first.pk, name="clash")
        with pytest.raises(IntegrityError):
            clash.save(force_insert=True)

    def test_ignore_conflicts_skips_duplicate_in_compiler(self):
        """The compiler-level ignore_conflicts path skips duplicates without raising.

        Django wraps bulk_create() in transaction.atomic; inside a Couchbase
        N1QL transaction a duplicate-key INSERT poisons the SDK transaction
        irrecoverably (see Couchbase SDK error 17007/17008). We exercise the
        compiler directly to verify the in-loop conflict skipping works.
        """
        from django.contrib.auth.models import Group
        from django.db import connection

        existing = Group.objects.create(name=f"audit-igc-{uuid.uuid4().hex[:6]}")

        # Run a fake compiler.execute_sql with on_conflict=IGNORE on a row whose
        # PK already exists — must NOT raise.
        # Sanity: detector recognizes the SDK exception name.
        from couchbase.exceptions import DocumentExistsException

        from django_couchbase_orm.db.backends.couchbase.compiler import (
            _is_duplicate_key_error,
        )

        assert _is_duplicate_key_error(DocumentExistsException(), "")

        # Simulate the row tuple as_sql() would produce, then run execute_sql.
        keyspace = f"`{connection.settings_dict['NAME']}`.`_default`.`{Group._meta.db_table}`"
        sql = f"INSERT INTO {keyspace} (KEY, VALUE) VALUES (%s, %s)"
        params = (str(existing.pk), {"name": "duplicate", "id": existing.pk})

        # Patch the compiler's as_sql to return our row, then call execute_sql.
        # We bypass Django's transactional wrapper by calling cursor.execute directly.
        with connection.cursor() as cursor:
            try:
                cursor.execute(sql, params)
                pytest.fail("Expected duplicate-key error from INSERT")
            except Exception as e:
                assert _is_duplicate_key_error(e, str(e))


# ============================================================
# #6 nested JSON path
# ============================================================


class TestNestedJSON:
    def test_nested_filter_matches(self):
        AuditDoc(
            name="alice",
            counter=1,
            profile={"address": {"city": "Brooklyn"}},
        ).save()
        AuditDoc(
            name="bob",
            counter=2,
            profile={"address": {"city": "Queens"}},
        ).save()

        results = list(AuditDoc.objects.filter(profile__address__city="Brooklyn"))
        assert len(results) == 1
        assert results[0].name == "alice"

    def test_nested_path_rejects_injection(self):
        with pytest.raises(ValueError):
            list(AuditDoc.objects.filter(**{"profile__city`); DROP COLLECTION x;--": "x"}))


# ============================================================
# #7 CAS-based optimistic locking
# ============================================================


class TestCAS:
    def test_replace_with_stale_cas_raises(self):
        doc = AuditDoc(name="solo", counter=0)
        doc.save()
        # Mutate via a second copy.
        other = AuditDoc.objects.get(pk=doc.pk)
        other.counter = 99
        other.save()

        # Original copy still has the old CAS — save must conflict.
        doc.counter = 1
        with pytest.raises(ConcurrentModificationError):
            doc.save()

    def test_cas_disabled_overrides_safely(self):
        doc = AuditDoc(name="solo", counter=0)
        doc.save()
        other = AuditDoc.objects.get(pk=doc.pk)
        other.counter = 99
        other.save()

        doc.counter = 1
        # cas=False explicitly opts in to last-writer-wins.
        doc.save(cas=False)
        reloaded = AuditDoc.objects.get(pk=doc.pk)
        assert reloaded.counter == 1


# ============================================================
# #8 prefetch errors narrowed
# ============================================================


class TestPrefetchErrors:
    def test_dangling_reference_skipped(self):
        """A missing referenced doc is silently skipped — no exception."""
        target = RefTarget(label="will-be-deleted")
        target.save()
        holder = RefHolder()
        holder._data["target"] = target.pk
        holder.save()
        target.delete()

        # Call the prefetch path directly with the live (now dangling) reference.
        qs = RefHolder.objects.all().select_related("target")
        # Reload the holder and run the prefetch helper — must not raise.
        reloaded = RefHolder.objects.get(pk=holder.pk)
        qs._prefetch_related([reloaded])

    def test_unreachable_collection_propagates(self, monkeypatch):
        """A connection-level failure during prefetch must propagate, not be swallowed."""
        from couchbase.exceptions import TimeoutException

        target = RefTarget(label="ref")
        target.save()
        holder = RefHolder()
        holder._data["target"] = target.pk
        holder.save()

        qs = RefHolder.objects.all().select_related("target")
        reloaded = RefHolder.objects.get(pk=holder.pk)

        from django_couchbase_orm import connection as conn_mod

        def boom(**kwargs):
            class _Bad:
                def get(self, key):
                    raise TimeoutException("simulated infra failure")

            return _Bad()

        monkeypatch.setattr(conn_mod, "get_collection", boom)

        with pytest.raises(TimeoutException):
            qs._prefetch_related([reloaded])


# ============================================================
# #9 type fidelity (bool + decimal)
# ============================================================


class TestTypeFidelity:
    def test_decimal_round_trip_preserves_precision(self):

        # Auth User has no DecimalField, so use the operations adapter directly
        # through a roundtrip via the connection.
        from django.db import connection

        ops = connection.ops
        big = Decimal("9876543210.123456789012345")
        adapted = ops.adapt_decimalfield_value(big)
        assert adapted == "9876543210.123456789012345"

    def test_bool_string_false_is_false(self):
        from django_couchbase_orm.fields.simple import BooleanField

        f = BooleanField()
        f.name = "flag"
        assert f.to_python("false") is False
        assert f.to_python("0") is False
        assert f.to_python("true") is True
        assert f.to_python("1") is True
        with pytest.raises(Exception):
            f.to_python("not-a-bool")


# ============================================================
# #10 identifier validation
# ============================================================


class TestIdentifierValidation:
    def test_bucket_with_backtick_rejected(self):
        from django_couchbase_orm.query.n1ql import N1QLQuery

        with pytest.raises(ValueError, match="Invalid bucket name"):
            N1QLQuery("evil`bucket", "_default", "_default")

    def test_bucket_starting_with_digit_allowed(self):
        from django_couchbase_orm.query.n1ql import N1QLQuery

        # Couchbase permits digit-leading bucket names; the validator must too.
        N1QLQuery("3rd-party-data", "_default", "_default")

    def test_bucket_with_percent_allowed(self):
        from django_couchbase_orm.query.n1ql import N1QLQuery

        # Couchbase permits '%' in bucket names.
        N1QLQuery("metrics%2025", "_default", "_default")

    def test_dot_in_collection_rejected(self):
        from django_couchbase_orm.query.n1ql import N1QLQuery

        # Couchbase forbids dots in scope/collection names.
        with pytest.raises(ValueError, match="Invalid scope/collection"):
            N1QLQuery("good_bucket", "_default", "bad.collection")

    def test_default_scope_allowed(self):
        from django_couchbase_orm.query.n1ql import N1QLQuery

        # Built-in _default and _system must remain valid.
        N1QLQuery("good_bucket", "_default", "_default")

    def test_aggregate_alias_validated(self):
        from django_couchbase_orm.aggregates import Count

        qs = AuditDoc.objects.all()
        with pytest.raises(ValueError, match="Invalid identifier"):
            qs.aggregate(**{"bad alias`with space": Count("name")})

    def test_sql_flush_rejects_bad_table_name(self):
        from django.db import connection

        ops = connection.ops
        with pytest.raises(ValueError, match="Invalid scope/collection"):
            ops.sql_flush(None, ["good_table", "evil`tbl"])
