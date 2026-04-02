# Changelog

## 0.2.0 (2026-04-01)

### New Features

- **Aggregation**: `aggregate()` with `Count`, `Sum`, `Avg`, `Min`, `Max` via N1QL
- **Pagination**: `CouchbasePaginator` with Django-style `Page` objects
- **Bulk operations**: `bulk_create()` and `bulk_update()` for batch KV operations
- **select_related**: Prefetch `ReferenceField` documents to avoid N+1 queries
- **Management commands**: `cb_ensure_indexes` and `cb_create_collections`
- **Login rate limiting**: 5 attempts, 5-minute cooldown

### Security Fixes

- Fixed session fixation (cycle session key on login)
- Fixed document ID injection (namespace-prefix + validation)
- Fixed timing attack in auth backend (constant-time hash on all paths)
- Added field name validation to prevent N1QL identifier injection
- Removed hardcoded default credentials
- Added URL scheme validation (blocks `javascript:` XSS)
- Added page parameter bounds validation (prevents DoS)
- Replaced raw N1QL query with QuerySet API
- Redacted session keys from error logs

### Improvements

- Renamed package to `django-couchbase-orm` on PyPI
- Added Railway deployment config (Dockerfile)
- Auto-detect Railway domain for ALLOWED_HOSTS
- Added GitHub Actions CI (lint, test Python 3.10-3.13, build)
- Added GitHub Actions publish workflow (trusted publishing via OIDC)

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
