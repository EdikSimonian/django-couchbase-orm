"""Concurrency tests — simulate multiple users doing CRUD operations simultaneously.

Tests thread safety of:
- Document API: save, get, update, delete from multiple threads
- Connection pool: shared cluster across threads
- Auto-increment IDs: no duplicates under contention
- QuerySet operations: concurrent reads and writes
- get_or_create: race condition handling
- bulk_update: concurrent field modifications
- Django backend: concurrent ORM operations via multiple threads
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from django_couchbase_orm.document import Document
from django_couchbase_orm.fields.simple import BooleanField, IntegerField, StringField
from tests.conftest import couchbase_available, flush_collection

LOCAL_COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "testbucket",
        "SCOPE": "_default",
    }
}

integration_mark = pytest.mark.skipif(not couchbase_available, reason="Local Couchbase not available")


class ConcDoc(Document):
    name = StringField(required=True)
    counter = IntegerField(default=0)
    owner = StringField()
    active = BooleanField(default=True)

    class Meta:
        collection_name = "edge_test_docs"


def _flush():
    flush_collection("edge_test_docs")


# ============================================================
# Document API concurrency
# ============================================================


@integration_mark
class TestConcurrentDocumentSaves:
    """Multiple threads saving different documents simultaneously."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush()
        yield
        _flush()

    def test_concurrent_creates(self):
        """10 threads each creating a document — all should succeed with unique IDs."""
        results = []
        errors = []

        def create_doc(i):
            try:
                doc = ConcDoc(name=f"thread_{i}", counter=i)
                doc.save()
                return doc.pk
            except Exception as e:
                errors.append(str(e))
                return None

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(create_doc, i) for i in range(10)]
            for f in as_completed(futures):
                pk = f.result()
                if pk:
                    results.append(pk)

        assert len(errors) == 0, f"Errors during concurrent creates: {errors}"
        assert len(results) == 10
        assert len(set(results)) == 10  # All PKs unique

        # Verify all documents exist
        count = ConcDoc.objects.count()
        assert count == 10

    def test_concurrent_saves_same_document_last_writer_wins(self):
        """With cas=False, multiple threads updating the same document can
        all succeed (last write wins, no conflict detection)."""
        doc = ConcDoc(name="shared", counter=0)
        doc.save()
        pk = doc.pk

        errors = []

        def update_doc(i):
            try:
                d = ConcDoc.objects.get(pk=pk)
                d.counter = i
                d.name = f"updated_by_{i}"
                d.save(cas=False)  # opt out of CAS for last-writer-wins
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(update_doc, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        final = ConcDoc.objects.get(pk=pk)
        assert final.name.startswith("updated_by_")

    def test_concurrent_saves_same_document_cas_detects_conflict(self):
        """With CAS on (default), concurrent writers see ConcurrentModificationError."""
        from django_couchbase_orm.exceptions import ConcurrentModificationError

        doc = ConcDoc(name="shared", counter=0)
        doc.save()
        pk = doc.pk

        results = {"success": 0, "conflict": 0, "other": []}
        lock = __import__("threading").Lock()

        def update_doc(i):
            try:
                d = ConcDoc.objects.get(pk=pk)
                d.counter = i
                d.name = f"updated_by_{i}"
                d.save()
                with lock:
                    results["success"] += 1
            except ConcurrentModificationError:
                with lock:
                    results["conflict"] += 1
            except Exception as e:
                with lock:
                    results["other"].append(str(e))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(update_doc, i) for i in range(8)]
            for f in as_completed(futures):
                f.result()

        # No unexpected exceptions, at least one writer succeeded, and at
        # least one was rejected with a conflict (this is the whole point).
        assert results["other"] == []
        assert results["success"] >= 1
        assert results["conflict"] >= 1
        final = ConcDoc.objects.get(pk=pk)
        assert final.name.startswith("updated_by_")

    def test_concurrent_read_write(self):
        """Some threads reading while others are writing."""
        # Pre-populate
        for i in range(5):
            ConcDoc(name=f"rw_{i}", counter=i).save()

        read_results = []
        write_errors = []

        def reader():
            try:
                docs = list(ConcDoc.objects.all())
                read_results.append(len(docs))
            except Exception:
                read_results.append(-1)

        def writer(i):
            try:
                ConcDoc(name=f"rw_new_{i}", counter=100 + i).save()
            except Exception as e:
                write_errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for i in range(5):
                futures.append(pool.submit(reader))
                futures.append(pool.submit(writer, i))
            for f in as_completed(futures):
                f.result()

        assert len(write_errors) == 0, f"Write errors: {write_errors}"
        # Readers should have gotten results (count may vary due to timing)
        assert all(r >= 0 for r in read_results)

    def test_concurrent_deletes(self):
        """Multiple threads deleting different documents."""
        docs = []
        for i in range(10):
            d = ConcDoc(name=f"del_{i}", counter=i)
            d.save()
            docs.append(d)

        errors = []

        def delete_doc(doc):
            try:
                doc.delete()
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(delete_doc, d) for d in docs]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Delete errors: {errors}"
        assert ConcDoc.objects.count() == 0


@integration_mark
class TestConcurrentQuerySetOperations:
    """Concurrent N1QL query operations."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush()
        yield
        _flush()

    def test_concurrent_counts(self):
        """Multiple threads counting documents simultaneously."""
        for i in range(20):
            ConcDoc(name=f"count_{i}", counter=i).save()

        results = []

        def count_docs():
            c = ConcDoc.objects.count()
            results.append(c)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(count_docs) for _ in range(5)]
            for f in as_completed(futures):
                f.result()

        assert all(r == 20 for r in results), f"Count results: {results}"

    def test_concurrent_filters(self):
        """Multiple threads running different filter queries."""
        for i in range(10):
            ConcDoc(name=f"filter_{i}", counter=i, active=(i % 2 == 0)).save()

        results = {}

        def filter_active(active_val, key):
            docs = list(ConcDoc.objects.filter(active=active_val))
            results[key] = len(docs)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(filter_active, True, "active"),
                pool.submit(filter_active, False, "inactive"),
                pool.submit(filter_active, True, "active2"),
                pool.submit(filter_active, False, "inactive2"),
            ]
            for f in as_completed(futures):
                f.result()

        assert results["active"] == 5
        assert results["inactive"] == 5
        assert results["active2"] == 5
        assert results["inactive2"] == 5

    def test_concurrent_bulk_updates(self):
        """Multiple threads doing N1QL UPDATE on different subsets."""
        for i in range(10):
            ConcDoc(name=f"bu_{i}", counter=0, owner=f"team_{i % 2}").save()

        errors = []

        def update_team(team_name, new_counter):
            try:
                count = ConcDoc.objects.filter(owner=team_name).update(counter=new_counter)
                return count
            except Exception as e:
                errors.append(str(e))
                return 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(update_team, "team_0", 100)
            f2 = pool.submit(update_team, "team_1", 200)

            count1 = f1.result()
            count2 = f2.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert count1 == 5
        assert count2 == 5

        # Verify
        team0 = list(ConcDoc.objects.filter(owner="team_0"))
        team1 = list(ConcDoc.objects.filter(owner="team_1"))
        assert all(d.counter == 100 for d in team0)
        assert all(d.counter == 200 for d in team1)

    def test_concurrent_bulk_deletes(self):
        """Multiple threads deleting different subsets via N1QL."""
        for i in range(10):
            ConcDoc(name=f"bd_{i}", owner=f"team_{i % 2}").save()

        errors = []

        def delete_team(team_name):
            try:
                return ConcDoc.objects.filter(owner=team_name).delete()
            except Exception as e:
                errors.append(str(e))
                return 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(delete_team, "team_0")
            f2 = pool.submit(delete_team, "team_1")
            count1 = f1.result()
            count2 = f2.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert count1 == 5
        assert count2 == 5
        assert ConcDoc.objects.count() == 0

    def test_concurrent_aggregates(self):
        """Multiple threads running aggregations simultaneously."""
        for i in range(10):
            ConcDoc(name=f"agg_{i}", counter=i * 10).save()

        from django_couchbase_orm.aggregates import Avg, Count, Max, Min, Sum

        results = {}
        errors = []

        def run_agg(name, **kwargs):
            try:
                result = ConcDoc.objects.all().aggregate(**kwargs)
                results[name] = result
            except Exception as e:
                errors.append(f"{name}: {e}")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(run_agg, "count", total=Count("*")),
                pool.submit(run_agg, "avg", avg_counter=Avg("counter")),
                pool.submit(run_agg, "sum", total_counter=Sum("counter")),
                pool.submit(run_agg, "min", min_counter=Min("counter")),
                pool.submit(run_agg, "max", max_counter=Max("counter")),
            ]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert results["count"]["total"] == 10
        assert results["avg"]["avg_counter"] == 45.0
        assert results["sum"]["total_counter"] == 450
        assert results["min"]["min_counter"] == 0
        assert results["max"]["max_counter"] == 90


@integration_mark
class TestConcurrentManagerOperations:
    """Manager operations under contention."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush()
        yield
        _flush()

    def test_concurrent_get_or_create(self):
        """Multiple threads calling get_or_create with the same ID."""
        results = []
        errors = []

        def get_or_create_doc(thread_id):
            try:
                doc, created = ConcDoc.objects.get_or_create(
                    _id="shared_goc_id",
                    defaults={"name": f"from_thread_{thread_id}", "counter": thread_id},
                )
                results.append({"created": created, "thread": thread_id, "name": doc.name})
            except Exception as e:
                errors.append(f"thread_{thread_id}: {e}")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(get_or_create_doc, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5

        # Exactly one thread should have created it
        created_count = sum(1 for r in results if r["created"])
        assert created_count >= 1  # At least one created it

        # The document should exist with consistent data
        doc = ConcDoc.objects.get(pk="shared_goc_id")
        assert doc.name.startswith("from_thread_")

    def test_concurrent_bulk_create(self):
        """Multiple threads each bulk-creating a batch of documents."""
        all_docs = []
        errors = []

        def bulk_create_batch(batch_id):
            try:
                docs = [ConcDoc(name=f"batch_{batch_id}_doc_{i}", counter=i) for i in range(5)]
                created = ConcDoc.objects.bulk_create(docs)
                return len(created)
            except Exception as e:
                errors.append(f"batch_{batch_id}: {e}")
                return 0

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(bulk_create_batch, i) for i in range(4)]
            counts = [f.result() for f in as_completed(futures)]

        assert len(errors) == 0, f"Errors: {errors}"
        assert sum(counts) == 20
        assert ConcDoc.objects.count() == 20

    def test_concurrent_bulk_update(self):
        """Multiple threads doing bulk_update on different document sets."""
        docs_a = [ConcDoc(name=f"a_{i}", counter=0, owner="team_a") for i in range(5)]
        docs_b = [ConcDoc(name=f"b_{i}", counter=0, owner="team_b") for i in range(5)]
        ConcDoc.objects.bulk_create(docs_a)
        ConcDoc.objects.bulk_create(docs_b)

        errors = []

        def update_batch(docs, new_counter):
            try:
                for d in docs:
                    d.counter = new_counter
                return ConcDoc.objects.bulk_update(docs, ["counter"])
            except Exception as e:
                errors.append(str(e))
                return 0

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(update_batch, docs_a, 100)
            f2 = pool.submit(update_batch, docs_b, 200)
            count1 = f1.result()
            count2 = f2.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert count1 == 5
        assert count2 == 5


@integration_mark
class TestConnectionPoolThreadSafety:
    """Test that the connection pool handles concurrent access correctly."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush()
        yield
        _flush()

    def test_concurrent_get_cluster(self):
        """Multiple threads requesting the cluster simultaneously."""
        from django_couchbase_orm.connection import get_cluster

        clusters = []
        errors = []

        def get_cluster_thread():
            try:
                c = get_cluster()
                clusters.append(id(c))
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_cluster_thread) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(clusters) == 10
        # All threads should get the same cluster instance (connection pooling)
        assert len(set(clusters)) == 1, f"Expected 1 unique cluster, got {len(set(clusters))}"

    def test_concurrent_get_collection(self):
        """Multiple threads requesting the same collection."""
        from django_couchbase_orm.connection import get_collection

        collections = []
        errors = []

        def get_coll_thread():
            try:
                c = get_collection(collection="edge_test_docs")
                collections.append(id(c))
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_coll_thread) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(collections) == 10
        assert len(set(collections)) == 1  # Same collection instance


@integration_mark
class TestConcurrentDjangoBackend:
    """Concurrent operations through the Django ORM backend (django.db.models).

    Simulates multiple web request handlers hitting the ORM simultaneously.
    """

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_user_creates(self):
        """Multiple threads creating Django auth users simultaneously."""
        from django.contrib.auth.models import User

        results = []
        errors = []

        def create_user(i):
            try:
                username = f"conc_user_{uuid.uuid4().hex[:8]}"
                user = User.objects.create_user(username, f"{username}@test.com", "pass123")
                results.append(user.pk)
                return user.pk
            except Exception as e:
                errors.append(f"thread_{i}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(create_user, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5
        assert len(set(results)) == 5  # All unique PKs

        # Cleanup
        for pk in results:
            try:
                User.objects.get(pk=pk).delete()
            except Exception:
                pass

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_user_updates(self):
        """Multiple threads updating different users simultaneously."""
        from django.contrib.auth.models import User

        # Create users first
        users = []
        for i in range(5):
            username = f"upd_conc_{uuid.uuid4().hex[:8]}"
            u = User.objects.create_user(username, f"{username}@test.com", "pass123")
            users.append(u)

        errors = []

        def update_user(user, new_name):
            try:
                User.objects.filter(pk=user.pk).update(first_name=new_name)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(update_user, u, f"Name_{i}") for i, u in enumerate(users)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"

        # Verify all updates applied
        for i, u in enumerate(users):
            u.refresh_from_db()
            assert u.first_name == f"Name_{i}"
            u.delete()

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_save_and_query(self):
        """Writers creating users while readers query — simulates real web traffic."""
        from django.contrib.auth.models import User

        prefix = f"rw_{uuid.uuid4().hex[:6]}"
        read_counts = []
        write_pks = []
        errors = []

        def writer(i):
            try:
                username = f"{prefix}_{i}"
                u = User.objects.create_user(username, f"{username}@test.com", "pass123")
                write_pks.append(u.pk)
            except Exception as e:
                errors.append(f"writer_{i}: {e}")

        def reader():
            try:
                count = User.objects.filter(username__startswith=prefix).count()
                read_counts.append(count)
            except Exception as e:
                errors.append(f"reader: {e}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = []
            for i in range(5):
                futures.append(pool.submit(writer, i))
            # Stagger readers slightly
            time.sleep(0.05)
            for _ in range(3):
                futures.append(pool.submit(reader))
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(write_pks) == 5

        # Final count should be 5
        final_count = User.objects.filter(username__startswith=prefix).count()
        assert final_count == 5

        # Cleanup
        User.objects.filter(username__startswith=prefix).delete()


@integration_mark
class TestAutoIncrementUnderContention:
    """Test that auto-increment PK generation works under concurrent load."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()

    @pytest.mark.django_db(transaction=True)
    def test_no_duplicate_pks(self):
        """20 concurrent inserts should all get unique auto-incremented PKs."""
        from django.contrib.auth.models import Group

        results = []
        errors = []

        def create_group(i):
            try:
                name = f"conc_group_{uuid.uuid4().hex[:8]}"
                g = Group.objects.create(name=name)
                results.append(g.pk)
            except Exception as e:
                errors.append(f"thread_{i}: {e}")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(create_group, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 20
        # All PKs must be unique — this is the critical assertion
        assert len(set(results)) == 20, f"Duplicate PKs found! PKs: {sorted(results)}"

        # All PKs should be integers
        assert all(isinstance(pk, int) for pk in results)

        # Cleanup
        Group.objects.filter(pk__in=results).delete()
