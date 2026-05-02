import os
import socket

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.django_settings")
django.setup()


# ============================================================
# Couchbase availability detection
# ============================================================


def _couchbase_available():
    """Check if a local Couchbase instance is reachable."""
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("localhost", 8091))
        s.close()
        return True
    except Exception:
        return False


# Expose as module-level for imports from other test files
couchbase_available = _couchbase_available()


@pytest.fixture(scope="session")
def couchbase_ready():
    """Session-scoped fixture that skips if Couchbase is not running.

    Usage:
        @pytest.mark.usefixtures("couchbase_ready")
        class TestSomething:
            ...
    """
    if not couchbase_available:
        pytest.skip("Local Couchbase not available — start with: docker compose -f docker-compose.test.yml up -d")


# ============================================================
# Shared test utilities
# ============================================================


def flush_collection(collection_name: str = "edge_test_docs"):
    """Delete all documents from a Couchbase test collection.

    Used by integration test fixtures for cleanup. Safe to call
    when Couchbase is not running (silently returns).
    """
    from django_couchbase_orm.connection import get_cluster, reset_connections

    reset_connections()
    try:
        from couchbase.n1ql import QueryScanConsistency
        from couchbase.options import QueryOptions

        cluster = get_cluster()
        cluster.query(
            f"DELETE FROM `testbucket`.`_default`.`{collection_name}`",
            QueryOptions(scan_consistency=QueryScanConsistency.REQUEST_PLUS),
        ).execute()
    except Exception:
        pass


# ============================================================
# Mock objects (kept for pure unit tests that don't need a database)
# ============================================================


class MockCASResult:
    """Mocks a Couchbase MutationResult with a CAS value."""

    def __init__(self, cas=12345):
        self.cas = cas


class MockGetResult:
    """Mocks a Couchbase GetResult."""

    def __init__(self, data: dict, cas=12345):
        self._data = data
        self.cas = cas
        self.content_as = {dict: data}


class MockExistsResult:
    """Mocks a Couchbase ExistsResult."""

    def __init__(self, exists=True):
        self.exists = exists


class MockCollection:
    """Mock Couchbase Collection for unit tests."""

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._cas_counter = 0
        self._cas_for_key: dict[str, int] = {}

    def _next_cas(self):
        self._cas_counter += 1
        return self._cas_counter

    def upsert(self, key, data, *args, **kwargs):
        self._store[key] = data
        cas = self._next_cas()
        self._cas_for_key[key] = cas
        return MockCASResult(cas)

    def insert(self, key, data, *args, **kwargs):
        if key in self._store:
            from couchbase.exceptions import DocumentExistsException

            raise DocumentExistsException()
        self._store[key] = data
        cas = self._next_cas()
        self._cas_for_key[key] = cas
        return MockCASResult(cas)

    def replace(self, key, data, *args, **kwargs):
        from couchbase.exceptions import (
            CasMismatchException,
            DocumentNotFoundException,
        )

        if key not in self._store:
            raise DocumentNotFoundException()
        # Look for cas in args[0] (Options object) or kwargs.
        provided_cas = kwargs.get("cas")
        if provided_cas is None and args:
            provided_cas = getattr(args[0], "cas", None) or getattr(args[0], "_cas", None)
        if provided_cas is not None and self._cas_for_key.get(key) != provided_cas:
            raise CasMismatchException()
        self._store[key] = data
        cas = self._next_cas()
        self._cas_for_key[key] = cas
        return MockCASResult(cas)

    def get(self, key, *args, **kwargs):
        if key not in self._store:
            from couchbase.exceptions import DocumentNotFoundException

            raise DocumentNotFoundException()
        return MockGetResult(self._store[key], self._cas_for_key.get(key, self._next_cas()))

    def remove(self, key, *args, **kwargs):
        if key not in self._store:
            from couchbase.exceptions import DocumentNotFoundException

            raise DocumentNotFoundException()
        del self._store[key]
        self._cas_for_key.pop(key, None)
        return MockCASResult(self._next_cas())

    def mutate_in(self, key, specs, *args, **kwargs):
        from couchbase.exceptions import (
            CasMismatchException,
            DocumentNotFoundException,
        )

        if key not in self._store:
            raise DocumentNotFoundException()
        provided_cas = kwargs.get("cas")
        if provided_cas is None and args:
            provided_cas = getattr(args[0], "cas", None) or getattr(args[0], "_cas", None)
        if provided_cas is not None and self._cas_for_key.get(key) != provided_cas:
            raise CasMismatchException()
        # Apply the specs as a flat dict update; only handle the upsert subdoc op.
        doc = self._store[key]
        for spec in specs:
            path = getattr(spec, "_path", None) or getattr(spec, "path", None)
            value = getattr(spec, "_value", None) or getattr(spec, "value", None)
            if path is None:
                continue
            doc[path] = value
        cas = self._next_cas()
        self._cas_for_key[key] = cas
        return MockCASResult(cas)

    def exists(self, key, *args, **kwargs):
        return MockExistsResult(key in self._store)


@pytest.fixture
def mock_collection():
    """Provide a MockCollection and patch get_collection to return it."""
    collection = MockCollection()
    return collection


@pytest.fixture
def patch_collection(mock_collection, monkeypatch):
    """Patch django_couchbase_orm.connection.get_collection to return the mock collection."""
    monkeypatch.setattr(
        "django_couchbase_orm.connection.get_collection",
        lambda **kwargs: mock_collection,
    )
    monkeypatch.setattr(
        "django_couchbase_orm.connection.get_collection",
        lambda alias="default", scope=None, collection=None: mock_collection,
    )
    return mock_collection
