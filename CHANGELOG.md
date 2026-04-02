# Changelog

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
