# Testing Guide

The project has **1,233+ tests** covering the full stack: Document API, Django database backend, Wagtail integration, concurrency, and edge cases. All tests run against a real Dockerized Couchbase instance.

## Quick Start

```bash
# Option 1: Full auto-setup (start Docker + configure + run migrations)
./scripts/setup-test-couchbase.sh --start

# Option 2: Manual steps
docker compose -f docker-compose.test.yml up -d
./scripts/setup-test-couchbase.sh

# Install dependencies
pip install -e ".[dev]" pytest-django pytest-asyncio wagtail

# Run all tests
pytest tests/ --ignore=tests/testapp --ignore=tests/wagtailapp

# Or: setup + test in one command
./scripts/setup-test-couchbase.sh --full
```

## Prerequisites

### Docker Couchbase (recommended)

```bash
docker compose -f docker-compose.test.yml up -d
./scripts/setup-test-couchbase.sh
```

This starts Couchbase Server, initializes the cluster, creates the `testbucket` bucket, and sets up indexes. The setup script is idempotent.

### Manual Couchbase Setup

If you already have Couchbase running:

1. Create a bucket named `testbucket` (128MB RAM quota)
2. Enable N1QL, Index, and KV services
3. Create a primary index on `testbucket._default._default`
4. Default credentials: `Administrator` / `password`

## Test Architecture

All tests run against **real Couchbase** — no mocks for query execution, mutations, or connection management. This ensures bugs like incorrect return types, missing scan consistency, and race conditions are caught.

```
tests/
  conftest.py                  # Shared fixtures, Couchbase availability check
  django_settings.py           # Django settings (auto-detects Wagtail)

  # Document API
  test_document.py             # Document CRUD, validation, serialization
  test_fields.py               # Field types: String, Integer, Float, Boolean, UUID
  test_compound_fields.py      # ListField, DictField, EmbeddedDocument
  test_datetime_fields.py      # DateTimeField, DateField, auto_now/auto_now_add
  test_reference_field.py      # ReferenceField, dereference, type resolution
  test_queryset.py             # QuerySet building: filter, exclude, order_by
  test_queryset_execution.py   # QuerySet execution against real Couchbase
  test_n1ql.py                 # N1QL query builder, parameterization
  test_q.py                    # Q objects: AND, OR, NOT, nesting
  test_aggregates.py           # Count, Sum, Avg, Min, Max
  test_paginator.py            # CouchbasePaginator, Page navigation
  test_manager.py              # DocumentManager: get, create, bulk ops
  test_connection.py           # Connection pooling, config validation
  test_signals.py              # pre_save, post_save, pre_delete, post_delete
  test_subdoc.py               # Sub-document operations
  test_select_related.py       # Reference prefetching
  test_bulk.py                 # bulk_create, bulk_update
  test_transforms.py           # Lookup transforms: exact, gt, in, contains...
  test_options.py              # DocumentOptions, Meta class
  test_exceptions.py           # Custom exception classes
  test_sessions.py             # Couchbase session backend
  test_auth.py                 # User model, password hashing, authentication
  test_async.py                # Async QuerySet: alist, acount, afirst, aget
  test_async_execution.py      # Async Document CRUD: asave, adelete, areload
  test_integration.py          # End-to-end Document API against real Couchbase

  # Django Database Backend
  test_backend_crud.py         # Phase 1: Connection, cursor, Model CRUD
  test_backend_phase2.py       # Phase 2: JOINs, M2M, annotations, F/Q objects
  test_backend_phase3.py       # Phase 3: Admin, auth, forms, sessions
  test_backend_phase4.py       # Phase 4: Migrations, schema editor, custom models
  test_backend_phase5.py       # Phase 5: Connection sharing, subqueries, bulk ops
  test_backend_security.py     # SQL injection prevention, password handling

  # Migration System
  test_migration_operations.py # CreateCollection, CreateIndex, AddField, RunN1QL
  test_migration_executor.py   # Migration execution, dependency resolution
  test_migration_autodetector.py # Auto-detecting model changes
  test_migration_writer.py     # Migration file generation
  test_migration_state.py      # Migration state tracking
  test_migration_commands.py   # cb_makemigrations, cb_migrate commands
  test_management.py           # cb_ensure_indexes, cb_create_collections

  # Wagtail Integration
  test_wagtail_crud.py         # Full page lifecycle: create, publish, update, delete

  # Reliability & Edge Cases
  test_edge_cases.py           # Boundary conditions, type coercion, null handling
  test_coverage_gaps.py        # N1QL builders, paginator, signals, document options
  test_concurrency.py          # Multi-threaded CRUD, connection pool, race conditions
```

## Test Suites by Count

| File | Tests | Category |
|------|------:|----------|
| `test_edge_cases.py` | 128 | Edge cases, regression tests |
| `test_coverage_gaps.py` | 114 | N1QL builders, paginator, signals, options |
| `test_fields.py` | 79 | Field validation, defaults, choices |
| `test_migration_operations.py` | 66 | Migration operations |
| `test_backend_crud.py` | 57 | Django backend CRUD |
| `test_document.py` | 46 | Document CRUD, serialization |
| `test_transforms.py` | 42 | Lookup transforms |
| `test_compound_fields.py` | 42 | List, Dict, Embedded fields |
| `test_integration.py` | 39 | Document API end-to-end |
| `test_backend_phase2.py` | 37 | JOINs, M2M, F/Q objects |
| `test_migration_writer.py` | 35 | Migration file generation |
| `test_datetime_fields.py` | 33 | DateTime, auto_now |
| `test_migration_executor.py` | 31 | Migration execution |
| `test_queryset.py` | 30 | QuerySet building |
| `test_migration_autodetector.py` | 29 | Change auto-detection |
| `test_wagtail_crud.py` | 28 | Wagtail page lifecycle |
| `test_auth.py` | 28 | Django auth integration |
| `test_queryset_execution.py` | 27 | QuerySet execution (real Couchbase) |
| `test_backend_security.py` | 27 | Security tests |
| `test_backend_phase3.py` | 23 | Admin, forms, sessions |
| `test_backend_phase5.py` | 21 | Subqueries, bulk ops |
| `test_n1ql.py` | 20 | N1QL query builder |
| `test_q.py` | 19 | Q objects |
| `test_reference_field.py` | 18 | ReferenceField |
| `test_concurrency.py` | 18 | Multi-threaded operations |
| `test_backend_phase4.py` | 18 | Migrations, schema editor |
| `test_paginator.py` | 17 | Pagination |
| `test_migration_state.py` | 17 | Migration state tracking |
| `test_manager.py` | 17 | DocumentManager |
| `test_async.py` | 17 | Async QuerySet |
| `test_subdoc.py` | 16 | Sub-document operations |
| `test_sessions.py` | 16 | Session backend |
| `test_async_execution.py` | 15 | Async CRUD |
| `test_connection.py` | 11 | Connection management |
| `test_migration_commands.py` | 10 | Management commands |
| `test_aggregates.py` | 10 | Aggregate functions |
| `test_signals.py` | 8 | Document signals |
| `test_bulk.py` | 8 | Bulk operations |
| `test_select_related.py` | 7 | Reference prefetching |
| `test_options.py` | 7 | DocumentOptions |
| `test_exceptions.py` | 6 | Exception classes |
| `test_production_readiness.py` | 17 | Error handling, logging, resource mgmt |
| `test_management.py` | 4 | Management commands |
| **Total** | **1,258** | |

## Concurrency Tests

The `test_concurrency.py` suite simulates multiple users hitting the ORM simultaneously using `ThreadPoolExecutor`. This catches thread-safety bugs in connection pooling, auto-increment ID generation, and race conditions.

| Test | Threads | What it simulates |
|------|--------:|-------------------|
| `test_concurrent_creates` | 10 | 10 users creating documents simultaneously |
| `test_concurrent_saves_same_document` | 5 | 5 users editing the same record |
| `test_concurrent_read_write` | 10 | Mixed read/write traffic |
| `test_concurrent_deletes` | 10 | 10 users deleting different records |
| `test_concurrent_counts` | 5 | Simultaneous COUNT(*) queries |
| `test_concurrent_filters` | 4 | Different filter queries in parallel |
| `test_concurrent_bulk_updates` | 2 | N1QL UPDATE on different subsets |
| `test_concurrent_bulk_deletes` | 2 | N1QL DELETE on different subsets |
| `test_concurrent_aggregates` | 5 | Different aggregations simultaneously |
| `test_concurrent_get_or_create` | 5 | Race condition: same ID, get_or_create |
| `test_concurrent_bulk_create` | 4 | Batch inserts from 4 threads |
| `test_concurrent_bulk_update` | 2 | Subdoc mutations on different sets |
| `test_concurrent_get_cluster` | 10 | Verifies connection pool returns same instance |
| `test_concurrent_get_collection` | 10 | Verifies collection caching |
| `test_concurrent_user_creates` | 5 | Django auth User creation |
| `test_concurrent_user_updates` | 5 | Django ORM update on different Users |
| `test_concurrent_save_and_query` | 8 | Writers + readers (simulates web traffic) |
| `test_no_duplicate_pks` | 10 | 20 concurrent inserts, all PKs must be unique |

## Running Specific Tests

```bash
# Single file
CB_BUCKET=testbucket pytest tests/test_concurrency.py

# Single test class
CB_BUCKET=testbucket pytest tests/test_edge_cases.py::TestUpdateReturnTypes

# Single test
CB_BUCKET=testbucket pytest tests/test_concurrency.py::TestAutoIncrementUnderContention::test_no_duplicate_pks

# By keyword
CB_BUCKET=testbucket pytest -k "concurrent"

# Backend tests only
CB_BUCKET=testbucket pytest tests/test_backend_*.py

# Wagtail tests only
CB_BUCKET=testbucket pytest tests/test_wagtail_crud.py

# Document API integration tests only
CB_BUCKET=testbucket pytest -m integration

# Verbose output
CB_BUCKET=testbucket pytest -v

# Stop on first failure
CB_BUCKET=testbucket pytest -x
```

## Coverage

```bash
# Full coverage (requires Couchbase)
CB_BUCKET=testbucket coverage run -m pytest tests/ \
  --ignore=tests/testapp --ignore=tests/wagtailapp
coverage report --show-missing --include="src/*"

# HTML report
coverage html
open htmlcov/index.html
```

## Test Configuration

Configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
DJANGO_SETTINGS_MODULE = "tests.django_settings"
markers = [
    "integration: tests that require a local Couchbase instance",
    "backend: Django database backend tests (require Couchbase)",
]
asyncio_mode = "auto"
```

Settings file: `tests/django_settings.py` — auto-detects Wagtail and adds its apps when available.

Environment variables for Couchbase connection:

| Variable | Default | Description |
|----------|---------|-------------|
| `CB_CONNECTION_STRING` | `couchbase://localhost` | Cluster connection string |
| `CB_USERNAME` | `Administrator` | Couchbase username |
| `CB_PASSWORD` | `password` | Couchbase password |
| `CB_BUCKET` | `testbucket` | Bucket name |
| `CB_SCOPE` | `_default` | Scope name |

## Writing New Tests

### Document API Test (integration)

```python
import pytest
from django_couchbase_orm.document import Document
from django_couchbase_orm.fields.simple import StringField
from tests.conftest import couchbase_available

LOCAL_COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "testbucket",
        "SCOPE": "_default",
    }
}

class MyDoc(Document):
    name = StringField(required=True)
    class Meta:
        collection_name = "edge_test_docs"  # Use existing collection

@pytest.mark.skipif(not couchbase_available, reason="Couchbase not available")
class TestMyFeature:
    @pytest.fixture(autouse=True)
    def _setup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections
        reset_connections()

    def test_something(self):
        doc = MyDoc(name="test")
        doc.save()
        loaded = MyDoc.objects.get(pk=doc.pk)
        assert loaded.name == "test"
```

### Django Backend Test

```python
import uuid
import pytest
from tests.conftest import couchbase_available

pytestmark = [
    pytest.mark.skipif(not couchbase_available, reason="Couchbase not available"),
    pytest.mark.django_db(transaction=True),
]

class TestMyBackendFeature:
    def test_model_crud(self):
        from django.contrib.auth.models import User
        username = f"test_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        assert user.pk is not None
        user.delete()
```

### Concurrency Test

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def test_concurrent_operation(self):
    errors = []

    def worker(i):
        try:
            MyDoc(name=f"thread_{i}").save()
        except Exception as e:
            errors.append(str(e))

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(worker, i) for i in range(10)]
        for f in as_completed(futures):
            f.result()

    assert len(errors) == 0, f"Errors: {errors}"
```

## CI/CD

Tests run automatically on push via GitHub Actions (`.github/workflows/ci.yml`).

The CI workflow:
1. **Lint** — Ruff check and format on Python 3.12
2. **Test** — Full test suite on Python 3.10, 3.11, 3.12, 3.13 with a Couchbase service container
3. **Build** — Build wheel and upload artifact

All tests (unit, integration, backend, Wagtail) run against a real Couchbase instance in CI. No mocks.

## Bugs Found by Tests

The test suite has caught these bugs:

| Bug | Found by | Fix |
|-----|----------|-----|
| `SQLUpdateCompiler.execute_sql()` returned cursor instead of int | `test_edge_cases.py::TestUpdateReturnTypes` | Changed `super()` call to use correct MRO |
| Missing `REQUEST_PLUS` scan consistency on reads | `test_queryset_execution.py` | Added `scan_consistency=REQUEST_PLUS` to all query methods |
| Missing `metrics=True` in update/delete | `test_edge_cases.py::TestUpdateReturnTypes` | Added `metrics=True` to `QueryOptions` |
| `UnsignedInt64` not cast to `int` | `test_edge_cases.py::TestDeleteEdgeCases` | Added `int()` cast on `mutation_count()` |
| `get_or_create` race condition | `test_concurrency.py::TestConcurrentManagerOperations` | Added retry on `DocumentExistsException` |
| Couchbase SDK segfault on connection close/reopen | `test_backend_crud.py` (all django_db tests) | Module-level cluster cache, skip SDK `close()` |
| Schema editor crash on transient index errors | Wagtail migration | Added retry with backoff for transient errors |
