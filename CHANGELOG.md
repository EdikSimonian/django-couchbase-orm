# Changelog

## 1.3.0 (unreleased) — audit-driven correctness pass

### Breaking changes

- **`INSERT INTO` (was `UPSERT INTO`)** — `Model.objects.create(...)` and `bulk_create(...)` now use real INSERT semantics. A duplicate primary key raises `django.db.IntegrityError` instead of silently overwriting. Use `bulk_create(objs, update_conflicts=True)` to keep upsert behavior.
- **N1QL errors propagate by default** — syntax errors and unsupported-pattern errors on SELECT now raise instead of being swallowed and returned as empty result sets. Set `OPTIONS['GRACEFUL_QUERY_ERRORS']=True` in `DATABASES` to restore the prior fail-soft behavior. The undocumented `"None("` heuristic was removed.
- **Transaction BEGIN failures raise** — a failed `BEGIN WORK` now raises `OperationalError` with an actionable message instead of silently autocommitting. Set `OPTIONS['TRANSACTIONS']='disabled'` to make `atomic()` a true no-op on clusters that do not support transactions.
- **Conservative feature flags** — `supports_over_clause`, `supports_select_union`, `supports_select_intersection`, `supports_select_difference`, `supports_partial_indexes`, and `supports_expression_indexes` are now `False`. Django will no longer generate SQL for these features that the cursor's regex SQL rewriter cannot reliably translate. Re-enable individually only after backend integration coverage lands.
- **`BooleanField` strict string parsing** — `BooleanField` now accepts only `bool`, `int`, and a small set of strings (`true`/`false`/`yes`/`no`/`0`/`1`/`""`, case-insensitive). Other strings raise `ValidationError`. Previously any non-empty string coerced to `True`, so `"false"` round-tripped to `True`.
- **`DecimalField` precision** — `DecimalField` is now serialized as a JSON string (round-tripped via `Decimal(str(...))`) instead of a JSON float, so values like `Decimal("1234567890.123456789012345")` survive exactly. Existing data stored as floats continues to read.

### New features

- **CAS-based optimistic locking on `Document.save()`** — by default, `save()` does an `insert` for new documents and a `replace` with the captured CAS for loaded documents. A concurrent writer raises the new `ConcurrentModificationError` (importable from `django_couchbase_orm`). Pass `save(cas=False)` for last-writer-wins. Queryset hydration now pulls `META(d).cas` alongside `META(d).id` (sync + async + select_related), so docs loaded via `.filter()` / `.get()` / `.iterator()` carry CAS too. `Manager.bulk_update(..., cas=True)` is the same.
- **Nested JSON paths** — Django-style nested lookups now produce real nested-document references: `Doc.objects.filter(profile__address__city="Brooklyn")` becomes `d.\`profile\`.\`address\`.\`city\` = $1`. Previously the whole path was treated as one flat key. Each segment is validated against the safe-identifier regex.
- **`OPTIONS['TRANSACTIONS']`** — `"enabled"` (default) or `"disabled"`. `"disabled"` skips `BEGIN WORK` entirely and reports `supports_transactions=False`.
- **`OPTIONS['GRACEFUL_QUERY_ERRORS']`** — `False` (default). Set to `True` to swallow N1QL 3000/4210 SELECT errors and return empty rows (legacy 1.2.x behavior, useful for data migrations that intentionally generate unsupported queries).

### Security / correctness

- **Identifier validation everywhere** — bucket/scope/collection names, `sql_flush` table names, and aggregate aliases now go through validators. Backticks/whitespace/SQL meta-characters are rejected. The bucket validator matches Couchbase's bucket naming rules (digit-leading and `%` allowed, ≤100 chars). The scope/collection validator forbids dots (per Couchbase rules) and allows leading underscores for built-in scopes (`_default`, `_system`).
- **Narrowed prefetch except** — `select_related()` prefetch (sync and async) now catches only `DocumentNotFoundException` for dangling references. Connection / auth / timeout errors propagate so they are visible.
- **`_find_existing_by_unique` honors custom PK columns** — previously it hardcoded `SELECT \`id\``, which broke uniqueness pre-checks and `OnConflict.UPDATE` targeting on models with custom primary key column names.

### Internal

- Cursor module docstring labels the `_fix_*` regex SQL rewriters as last-resort compatibility shims; new translations should land as Django compiler hooks.
- `_create_unique_index` clearly documents that N1QL has no `UNIQUE INDEX` type — the index it creates is a plain non-enforcing lookup index that speeds up the best-effort multi-field uniqueness pre-check.

### Stats

- 1,275 tests pass against real Couchbase (was 1,253 in 1.2.x). Added `tests/test_audit_fixes.py` (17 live tests) and 5 nested-path transform tests. Updated tests for new behavior on bool/decimal/CAS/feature-flags.

---

## 1.2.0 (2026-04-13)

### New Features

- **Timezone-aware datetimes** — DateTimeField now stores values with UTC offset (`+00:00`) and returns timezone-aware datetimes when Django's `USE_TZ=True`. Both the ORM backend (`operations.py`) and the Document API (`fields/datetime.py`) are timezone-aware. Naive datetimes are assumed UTC when `USE_TZ=True`, matching Django convention.

- **Unique constraint enforcement** — Fields with `unique=True` now raise `django.db.IntegrityError` on duplicate values instead of silently overwriting. Also checks `unique_together` and `UniqueConstraint` from `Meta.constraints`. Respects `bulk_create(ignore_conflicts=True)` to skip duplicates silently and `bulk_create(update_conflicts=True)` to update existing documents.

- **Window functions** — Enabled `supports_over_clause=True`. N1QL supports window functions (`ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, etc.) since Couchbase Server 6.5.

- **Prepared statement caching** — New `ADHOC` option in `DATABASES.OPTIONS`. Set to `False` to enable server-side query plan caching via `adhoc=False` on `QueryOptions`. Reduces parse overhead for repeated queries.

- **OpenTelemetry tracing** — New `TRACER` option in `DATABASES.OPTIONS` and `COUCHBASE.OPTIONS`. Pass an OpenTelemetry `TracerProvider` for zero-code query-level tracing on every SDK operation (Couchbase Python SDK 4.6+).

- **N1QL query_context** — All queries now set `query_context` to the default bucket/scope, so unqualified collection names in raw SQL or migrations resolve correctly server-side.

- **ACID transaction support** — `transaction.atomic()` now uses real Couchbase ACID transactions via N1QL `BEGIN WORK` / `COMMIT WORK` / `ROLLBACK WORK` with `txid` parameter tracking. All DML types (INSERT, UPDATE, DELETE, SELECT) work inside transactions. New `DURABILITY_LEVEL` option in `DATABASES.OPTIONS` — defaults to `"none"` (works on single-node dev clusters), set to `"majority"` for production multi-node clusters with replicas. Graceful error handling with actionable messages when durability is misconfigured. `supports_transactions=True` and `atomic_transactions=True` feature flags enabled.

### Bug Fixes

- **Fixed introspection query params** — `get_constraints()` was passing query parameters as positional args to `cluster.query()` instead of via `QueryOptions`. Parameters were being silently ignored, returning unfiltered results.

- **Fixed test bucket name mismatch** — `django_settings.py` defaulted to `test_bucket` but all tests and CI used `testbucket`. Aligned to `testbucket` everywhere.

### Improvements

- **Improved setup script** — `scripts/setup-test-couchbase.sh` now auto-creates Document API test collections + indexes, runs Django migrations, supports `--start` (Docker) and `--full` (Docker + tests) flags, and handles already-initialized clusters.

### SDK Compatibility

- Verified compatible with Couchbase Python SDK 4.6.0 (latest). No breaking changes from SDK 4.1→4.6 affect this ORM. Noted: `CollectionSpec` API is deprecated in SDK 4.6 (warning logged during schema operations).

### Stats

- 1,240 tests pass against real Couchbase (0 failures, 0 skipped, ~4 minutes)
- Python 3.10, 3.11, 3.12, 3.13, 3.14 supported

---

## 1.1.0 (2026-04-09)

### Critical Bug Fixes

- **Fixed UPDATE operations returning cursor instead of int** — `SQLUpdateCompiler.execute_sql()` used wrong `super()` call, bypassing Django's `rowcount` extraction. This broke `model.save()`, `QuerySet.update()`, login (`last_login` update), and any code doing `_update(values) > 0`. ([compiler.py:330](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/src/django_couchbase_orm/db/backends/couchbase/compiler.py#L330))
- **Fixed missing `REQUEST_PLUS` scan consistency on reads** — Document API queries (`_execute()`, `count()`, `aggregate()`, `iterator()`, `raw()`) used eventual consistency by default, causing reads to return stale data after writes.
- **Fixed `update()` and `delete()` returning 0 for successful mutations** — Missing `metrics=True` in `QueryOptions` meant the Couchbase SDK never populated `mutation_count`. Also fixed `UnsignedInt64` not being cast to `int`.
- **Fixed `get_or_create()` race condition** — Concurrent calls with the same `_id` caused `DocumentExistsException`. Now retries `get()` on duplicate key error.
- **Fixed Couchbase SDK segfault on connection close/reopen** — `pytest-django` and Django's `TransactionTestCase` close and reopen DB connections, triggering a segfault in the SDK's C++ layer. Fixed with module-level cluster cache and `close()` override that preserves the connection.

### Performance

- **Configurable scan consistency** — New `SCAN_CONSISTENCY` setting in COUCHBASE config. Defaults to `request_plus` (strong consistency). Set to `not_bounded` for read-heavy apps that can tolerate stale reads (~50-100ms savings per query).
- **Async queries now use consistent scan level** — `_async_execute()` and `acount()` previously defaulted to `NOT_BOUNDED`; now uses the same configured level as sync queries.

### Security

- **Removed default password fallback** — `get_or_create_couchbase_settings()` no longer defaults to `"password"` when PASSWORD is not configured. Logs a warning instead.
- **Redacted query text in error logs** — N1QL error logs now replace positional parameters (`$1`, `$2`) with `$?` to prevent sensitive WHERE clause data from leaking to log files.
- **Document `_id` type enforcement** — Non-string `_id` values are now coerced to `str()` instead of silently accepting wrong types.

### Production Readiness

- **Added logging to 16 silent error handlers** — All bare `except Exception: pass` patterns across `connection.py`, `schema.py`, `introspection.py`, `fields.py`, `cursor.py`, `base.py`, and `async_connection.py` now log with context.
- **Fixed `manager.exists()` swallowing all exceptions** — Now only catches `DocumentNotFoundException`; connection errors propagate.
- **N1QL errors 3000/4210 logged at ERROR level** — Previously logged at WARNING; now clearly indicates queries that need rewriting for Couchbase.
- **Added `cleanup_stale_connections()`** — New function to prune dead cluster/bucket/collection entries from the connection cache. Call periodically in long-running servers.
- **Added `reset_cached_clusters()`** — Clears the Django backend's module-level cluster cache. Call in Gunicorn `pre_fork` hook for clean worker recycling.
- **Schema editor retries on transient index errors** — `add_index()` now retries up to 3 times with backoff when Couchbase returns "Build Already In Progress".

### Testing Infrastructure

- **1,258 tests** — up from 940, all running against real Dockerized Couchbase (no mocks for query execution).
- **Docker Compose test setup** — `docker-compose.test.yml` + `scripts/setup-test-couchbase.sh` for one-command local testing.
- **Unified CI** — All tests (unit, integration, backend, Wagtail) run in a single GitHub Actions job with Couchbase service container on Python 3.10-3.13.
- **New test suites**:
  - `test_edge_cases.py` (128 tests) — boundary conditions, type coercion, null handling, return type regressions
  - `test_coverage_gaps.py` (114 tests) — N1QL builders, paginator, signals, document options, aggregate+filter combos
  - `test_concurrency.py` (18 tests) — multi-threaded CRUD, connection pool safety, auto-increment contention, `get_or_create` race
  - `test_production_readiness.py` (17 tests) — error logging verification, `exists()` error propagation, resource cleanup
  - `test_queryset_execution.py` rewritten — replaced mocked tests with real Couchbase execution
- **Wagtail tests fixed** — all 28 Wagtail CRUD tests now pass with correct settings auto-detection.
- **Shared test utilities** — `flush_collection()` in conftest.py replaces 5 duplicate cleanup functions.

### Code Quality

- **Ruff clean** — all lint checks pass (`ruff check src/`)
- **Deduplicated signal imports** — moved to module level in `document.py`
- **Removed unused imports** — cleaned up leftover `QueryScanConsistency` imports after refactoring

### Stats

- 1,258 tests (all against real Couchbase), 42 test modules
- Python 3.10, 3.11, 3.12, 3.13 supported
- Ruff: all checks passed
- 7 critical/high bugs fixed, 16 silent error handlers replaced with logging

---

## 1.0.0 (2026-04-05)

### Highlights

- **Django Database Backend** — Full `django.db.backends` implementation for Couchbase. Standard Django models, migrations, admin, auth, sessions, forms, DRF, and Wagtail work transparently.
- **Wagtail CMS support** — Full page tree, publishing, revisions, admin, search.
- **Combined with Document API** — Both APIs share the same Couchbase connection.

---

## 0.6.0 (2026-04-02)

### New Features

- **Migrations framework**: Django-style migrations for Couchbase with auto-detection, dependency resolution, and reversibility
  - **12 operations**: `CreateScope`, `DropScope`, `CreateCollection`, `DropCollection`, `CreateIndex`, `DropIndex`, `AddField`, `RemoveField`, `RenameField`, `AlterField`, `RunN1QL`, `RunPython`
  - **Auto-detection**: `cb_makemigrations` diffs current Document classes against stored state to generate operations automatically
  - **Dependency resolution**: Topological sort with circular dependency detection, cross-app dependencies
  - **Migration state**: Tracked in Couchbase document (`_cb_migrations`), no relational DB needed
  - **Migration writer**: Generates valid Python migration files with proper imports
  - **Reversibility**: Forward and reverse operations, with guards against irreversible rollbacks
  - **Fake migrations**: `--fake` flag to mark migrations as applied without executing
- **Management commands**: `cb_makemigrations` and `cb_migrate` with `--dry-run`, `--empty`, `--initial`, `--list`, `--fake` flags
- **Example app**: Migration status page with nav link, sample migration file with 5 indexes

### Stats

- 784 tests (745 unit + 39 integration), 188 new migration tests
- All CI jobs green: lint, test (Python 3.10-3.13), integration, build

## 0.5.0 (2026-04-02)

### New Features

- **Integration tests**: 39 tests against a real Couchbase instance (Docker) covering CRUD, QuerySet, aggregation, pagination, compound fields, references, select_related, signals, sub-document ops, timestamps, bulk operations
- **CI integration testing**: Couchbase Docker service in GitHub Actions with N1QL readiness checks
- **Coverage badges**: Auto-updating coverage badge via GitHub Gist + shields.io
- **README badges**: CI status, PyPI version, Python versions, coverage, license

### Fixes

- Fixed `subdoc.get()` and `subdoc.count()` to use `result.value[0]["value"]` for type-preserving access (discovered by integration tests)
- Fixed CI N1QL service readiness — added polling loop before running integration tests
- Fixed settings.py `DEBUG` ordering before `SECRET_KEY` check

### Stats

- 596 tests (557 unit + 39 integration), 91% coverage
- All CI jobs green: lint, test (Python 3.10-3.13), integration, build

## 0.4.0 (2026-04-02)

### New Features

- **Async support**: Full async API for Document (`asave`, `adelete`, `areload`), QuerySet (`acount`, `afirst`, `aget`, `aexists`, `alist`, `__aiter__`), and Manager (`acount`, `afirst`, `aget`, `acreate`, `alist`)
- **Async connection module**: `async_connection.py` using `acouchbase` SDK
- **Connection pre-warming**: Background thread connects to Couchbase on app startup, eliminating cold-start latency
- **Prepared statements**: All N1QL queries use `adhoc=False` for cached query plans (~30-50% faster)
- **In-memory query cache**: Home page counts and beer styles dropdown cached for 5 minutes

### Performance

- Example app async views with `asyncio.gather()` — home page 3x faster, list pages 2-3x faster
- Switched example from gunicorn/WSGI to uvicorn/ASGI

## 0.3.0 (2026-04-02)

### Breaking Change

- **Import renamed**: `from django_cb import ...` is now `from django_couchbase_orm import ...`
- Package name and import name now match consistently

### New Features

- **Aggregation**: `aggregate()` with `Count`, `Sum`, `Avg`, `Min`, `Max` via N1QL
- **Pagination**: `CouchbasePaginator` with Django-style `Page` objects
- **Bulk operations**: `bulk_create()` and `bulk_update()` for batch KV operations
- **select_related**: Prefetch `ReferenceField` documents to avoid N+1 queries
- **Management commands**: `cb_ensure_indexes` and `cb_create_collections`

## 0.2.0 (2026-04-01)

### Security Fixes (15 total)

- **Critical**: Fixed session fixation — session key now cycled on login via `cycle_key()`
- **Critical**: Fixed document ID injection — user-supplied IDs are namespace-prefixed (`brewery::`, `beer::`) and validated against `^[a-z0-9][a-z0-9_\-]{0,127}$`
- **High**: Fixed timing attack in auth backend — uses pre-computed unusable hash on all failure paths
- **High**: Fixed page parameter DoS — validates and bounds page number, caps at 10,000
- **High**: Removed hardcoded bucket name from raw N1QL — replaced with QuerySet API
- **Medium**: Added N1QL identifier validation — all field names checked against `^[a-zA-Z_]\w*$`
- **Medium**: Removed hardcoded default credentials — production fails without `DJANGO_SECRET_KEY`
- **Medium**: Added safe float parsing — rejects `NaN`/`Inf` in user input
- **Medium**: Added URL scheme validation — blocks `javascript:` URIs (stored XSS prevention)
- **Medium**: Improved `has_usable_password` — uses Django's canonical `is_password_usable()`
- **Medium**: Added session hash verification note
- **Low**: Redacted session keys from error logs
- **Low**: Added input length caps (200 chars) on search/filter parameters
- **Low**: Login rate limiting — 5 failed attempts triggers 5-minute lockout

### Improvements

- Renamed package to `django-couchbase-orm` on PyPI
- Added Railway deployment config (Dockerfile)
- Auto-detect Railway domain for ALLOWED_HOSTS
- Added GitHub Actions CI (lint, test Python 3.10-3.13, build)
- Added GitHub Actions publish workflow (trusted publishing via OIDC)
- All dependencies at latest versions, 0 CVEs (pip-audit clean)

## 0.1.0 (2026-04-01)

Initial release.

### Features

- **Document model** with metaclass, typed fields, validation, and CRUD operations
- **Fields**: StringField, IntegerField, FloatField, BooleanField, UUIDField, DateTimeField, DateField, ListField, DictField, EmbeddedDocumentField, ReferenceField
- **QuerySet** with Django-style filtering, ordering, slicing, Q objects, and 16 lookup transforms
- **N1QL query builder** with parameterized queries
- **KV-optimized** `get(pk=...)` for fast single-document lookups
- **Sub-document operations** via `document.subdoc` accessor
- **Signals**: pre_save, post_save, pre_delete, post_delete
- **Session backend**: Couchbase-backed Django sessions with TTL expiry
- **Auth backend**: Couchbase-backed User model and authentication
- **Connection management**: Thread-safe, lazy initialization, multiple connection support, automatic WAN profile for Capella
