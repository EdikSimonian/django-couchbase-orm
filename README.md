# django-couchbase-orm

[![CI](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml/badge.svg)](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/EdikSimonian/81d4c53b76d523240e3213a0a9f4b3b7/raw/coverage.json)](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/django-couchbase-orm?cacheSeconds=60)](https://pypi.org/project/django-couchbase-orm/)
[![Python](https://img.shields.io/pypi/pyversions/django-couchbase-orm)](https://pypi.org/project/django-couchbase-orm/)
[![License](https://img.shields.io/github/license/EdikSimonian/django-couchbase-orm)](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/LICENSE)

> **Live Demo:** [brewsync.simonian.online](https://brewsync.simonian.online) · [iOS app](https://apps.apple.com/us/app/brewsync-catalog/id6761658679)
> A full Django + Wagtail CMS + DRF beer catalog running on Couchbase Capella. Browse [beers](https://brewsync.simonian.online/beers/), read the [blog](https://brewsync.simonian.online/blog/), or explore the [Wagtail admin](https://brewsync.simonian.online/admin/).

Use Couchbase as your Django database. Drop-in backend for `django.db.models.Model` plus a standalone Document API for Couchbase-native patterns.

**Docs:** [Database Backend](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/database-backend.md) | [Document API](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/document-api.md) | [Wagtail](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/wagtail.md) | [Hybrid Architecture](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/hybrid.md) | [Testing](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/testing.md)

## Two Ways to Use It

### 1. Django Database Backend

Standard Django models work transparently with Couchbase. Admin, forms, DRF, Wagtail - everything just works.

```python
# settings.py
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "mybucket",
        "USER": "Administrator",
        "PASSWORD": "password",
        "HOST": "couchbase://localhost",
    }
}
DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"

# models.py - standard Django models, no changes needed
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Everything works: `makemigrations`, `migrate`, `createsuperuser`, Django admin, ModelForms, DRF serializers, Wagtail CMS.

### 2. Document API

For Couchbase-native patterns - subdoc operations, KV fast-path, embedded documents.

```python
# settings.py
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "mybucket",
    }
}

# documents.py
from django_couchbase_orm import Document, StringField, FloatField

class Beer(Document):
    name = StringField(required=True)
    abv = FloatField()
    style = StringField()

    class Meta:
        collection_name = "beers"
```

Both APIs can coexist in the same project. They share the same Couchbase connection.

## Install

```bash
pip install django-couchbase-orm
```

Requires Python 3.10+, Django 4.2+, Couchbase SDK 4.1+.

## Django Backend Features

Everything you'd expect from a Django database backend:

- `manage.py migrate` creates Couchbase collections
- `manage.py createsuperuser` works
- `ForeignKey`, `ManyToManyField` with JOINs via N1QL
- `select_related()`, `prefetch_related()`
- `annotate()`, `aggregate()` with `Count`, `Sum`, `Avg`, `Min`, `Max`
- `Q()` objects, `F()` expressions
- All lookups: `exact`, `icontains`, `startswith`, `in`, `isnull`, `regex`, etc.
- `values()`, `values_list()`, `distinct()`, `only()`, `defer()`
- `bulk_create()`, `bulk_update()`
- Django admin: list, add, edit, delete, search
- Django auth: users, groups, permissions
- Django sessions (DB backend)
- ContentTypes framework
- ModelForm, DRF ModelSerializer
- Wagtail CMS (page tree, publishing, admin)

### SQL-to-N1QL Translation

The backend transparently handles the differences between SQL and N1QL:

| SQL | N1QL (handled automatically) |
|-----|-----|
| `INSERT INTO` | `INSERT INTO` (raises `IntegrityError` on duplicate PK; use `update_conflicts=True` for upsert) |
| `SUBSTRING(s, pos)` | `SUBSTR(s, pos-1)` (0-indexed) |
| `IS NULL` | `IS NOT VALUED` (handles MISSING) |
| `CAST(x AS INT)` | `TONUMBER(x)` |
| `AUTO_INCREMENT` | Atomic counter (`binary.increment`) |
| Sequential IDs | `CouchbaseAutoField` (integer PKs) |

### Wagtail Support

Wagtail CMS works fully with the Couchbase backend. See the [live demo](https://brewsync.simonian.online/admin/) for a working example.

```python
INSTALLED_APPS = [
    ...
    "wagtail", "wagtail.admin", "wagtail.images",
    "wagtail.documents", "wagtail.search",
]

# manage.py migrate - creates all Wagtail collections
# manage.py createsuperuser - create admin user
# Page tree, publishing, editing, images, documents all work
```

### Couchbase Capella (Cloud)

Works with Couchbase Capella out of the box:

```python
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "my-bucket",
        "USER": "dbuser",
        "PASSWORD": "dbpassword",
        "HOST": "couchbases://cb.xxxxx.cloud.couchbase.com",
    }
}
```

## Document API Features

For when you need Couchbase-native performance:

- KV-optimized `get(pk=...)` (~1ms vs ~50ms for N1QL)
- Sub-document operations (partial reads/writes)
- Embedded documents
- Django-style QuerySet with N1QL
- Signals: `pre_save`, `post_save`, `pre_delete`, `post_delete`
- Async support (`asave`, `adelete`, `alist`, `acount`)
- Custom migrations framework (`cb_makemigrations`, `cb_migrate`)

### Quick Example

```python
from django_couchbase_orm import Document, StringField, FloatField, Q

# CRUD
beer = Beer(name="IPA", abv=6.5, style="IPA")
beer.save()
beer = Beer.objects.get(pk="beer-id")   # fast KV lookup
beer.abv = 7.0
beer.save()
beer.delete()

# Queries
Beer.objects.filter(style="IPA", abv__gte=6.0).order_by("-abv")[:20]
Beer.objects.filter(Q(style="IPA") | Q(style="Pale Ale")).count()
Beer.objects.aggregate(avg_abv=Avg("abv"), total=Count("*"))

# Sub-document operations
beer.subdoc.upsert("ratings.average", 4.5)
beer.subdoc.increment("view_count", 1)
beer.subdoc.array_append("tags", "hoppy")
```

## Configuration

### Database Backend (recommended)

```python
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "mybucket",          # Couchbase bucket
        "USER": "Administrator",
        "PASSWORD": "password",
        "HOST": "couchbase://localhost",
        "OPTIONS": {
            "SCOPE": "_default",     # optional
        },
    }
}
DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"
```

### Document API

```python
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "mybucket",
        "SCOPE": "_default",
    }
}
```

If you use the database backend, the Document API auto-derives its config from `DATABASES` - no need to set both.

## Fields (Document API)

| Field | Type | Options |
|-------|------|---------|
| `StringField` | `str` | `min_length`, `max_length`, `regex` |
| `IntegerField` | `int` | `min_value`, `max_value` |
| `FloatField` | `float` | `min_value`, `max_value` |
| `BooleanField` | `bool` | |
| `UUIDField` | `uuid.UUID` | `auto=True` |
| `DateTimeField` | `datetime` | `auto_now`, `auto_now_add` |
| `DateField` | `date` | `auto_now`, `auto_now_add` |
| `ListField` | `list` | `field` for typed elements |
| `DictField` | `dict` | |
| `EmbeddedDocumentField` | nested | |
| `ReferenceField` | FK-like | |

## Known Limitations

- **Transactions**: `atomic()` issues N1QL `BEGIN WORK`/`COMMIT WORK`/`ROLLBACK WORK`. The default `DURABILITY_LEVEL='none'` works on both single-node and multi-node clusters; raising durability above `'none'` requires replica nodes. If `BEGIN WORK` fails the call now raises `OperationalError` rather than silently autocommitting — set `OPTIONS['TRANSACTIONS']='disabled'` on `DATABASES` to opt out and make `atomic()` a true no-op.
- **INSERT semantics**: `Model.objects.create(...)` and `bulk_create(...)` now use `INSERT INTO` and raise `IntegrityError` on a duplicate PK instead of silently overwriting. Use `bulk_create(objs, update_conflicts=True)` for upsert behavior.
- **Document API CAS**: `Document.save()` does an optimistic-lock `replace` with the CAS captured at load time and raises `ConcurrentModificationError` on conflict. Pass `save(cas=False)` for last-writer-wins.
- **Query errors**: N1QL syntax/unsupported-pattern errors now propagate by default. Set `OPTIONS['GRACEFUL_QUERY_ERRORS']=True` if you want the prior fail-soft behavior for SELECT (returns empty results, logs the error).
- **Window functions / UNION / partial / expression indexes**: not advertised as supported. Re-enable individually only after backend integration coverage is added.
- **Page moves**: Wagtail page tree moves use raw SQL with reserved words. Use delete + recreate as a workaround.
- **Multi-table inheritance**: Works but may have performance implications with N1QL JOINs.

## Tests

**1,275 tests** across 48 test modules, tested on Python 3.10 - 3.14. All tests run against a real Dockerized Couchbase instance — no mocks for query execution.

| Suite | Tests | What's Covered |
|-------|------:|----------------|
| Document API | 784 | Fields, QuerySet, Manager, Document CRUD, signals, pagination, migrations, auth, sessions |
| Django Backend | 156 | Connection, cursor, CRUD, JOINs, M2M, admin, forms, migrations, subqueries, bulk ops |
| Edge Cases | 128 | Boundary conditions, type coercion, null handling, return types, regression tests |
| Coverage Gaps | 114 | N1QL builders, paginator, signals, document options, aggregate+filter combos |
| Wagtail CRUD | 28 | Page create, publish, edit, unpublish, delete, revisions, admin forms |
| Security | 27 | Injection prevention, password isolation, backtick escaping |
| Concurrency | 18 | Multi-threaded CRUD, connection pool thread safety, race conditions, auto-increment contention |

```bash
# Start Couchbase
docker compose -f docker-compose.test.yml up -d
./scripts/setup-test-couchbase.sh

# Run all tests
CB_BUCKET=testbucket pytest tests/ --ignore=tests/testapp --ignore=tests/wagtailapp

# Coverage
CB_BUCKET=testbucket coverage run -m pytest tests/ && coverage report --include="src/*"
```

See [Testing Guide](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/docs/testing.md) for full details.

## Example Project

The [`example/`](https://github.com/EdikSimonian/django-couchbase-orm/tree/main/example) directory contains a complete Django + Wagtail + DRF project (BrewSync) deployed at the [live demo](https://brewsync.simonian.online). It includes:

- Wagtail CMS with HomePage, BlogIndexPage, BlogPage
- Beer catalog with Brewery/Beer models
- DRF REST API (`/api/beers/`, `/api/breweries/`)
- Dark brewery theme with search and filtering
- Deployed on Railway with Couchbase Capella

## Development

```bash
git clone https://github.com/EdikSimonian/django-couchbase-orm.git
cd django-couchbase-orm
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history and migration notes.

## License

Apache 2.0
