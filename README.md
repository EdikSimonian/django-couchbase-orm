# django-couchbase-orm

[![CI](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml/badge.svg)](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/EdikSimonian/81d4c53b76d523240e3213a0a9f4b3b7/raw/coverage.json)](https://github.com/EdikSimonian/django-couchbase-orm/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/django-couchbase-orm?cacheSeconds=60)](https://pypi.org/project/django-couchbase-orm/)
[![Python](https://img.shields.io/pypi/pyversions/django-couchbase-orm)](https://pypi.org/project/django-couchbase-orm/)
[![License](https://img.shields.io/github/license/EdikSimonian/django-couchbase-orm)](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/LICENSE)

> **Live Demo:** [django-couchbase-orm-production.up.railway.app](https://django-couchbase-orm-production.up.railway.app)
> A full Django + Wagtail CMS + DRF beer catalog running on Couchbase Capella. Browse [beers](https://django-couchbase-orm-production.up.railway.app/beers/), read the [blog](https://django-couchbase-orm-production.up.railway.app/blog/), or explore the [Wagtail admin](https://django-couchbase-orm-production.up.railway.app/admin/).

Use Couchbase as your Django database. Drop-in backend for `django.db.models.Model` plus a standalone Document API for Couchbase-native patterns.

**Docs:** [Database Backend](docs/database-backend.md) | [Document API](docs/document-api.md) | [Wagtail](docs/wagtail.md) | [Hybrid Architecture](docs/hybrid.md) | [Testing](docs/testing.md)

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
| `INSERT INTO` | `UPSERT INTO` (idempotent) |
| `SUBSTRING(s, pos)` | `SUBSTR(s, pos-1)` (0-indexed) |
| `IS NULL` | `IS NOT VALUED` (handles MISSING) |
| `CAST(x AS INT)` | `TONUMBER(x)` |
| `AUTO_INCREMENT` | Atomic counter (`binary.increment`) |
| Sequential IDs | `CouchbaseAutoField` (integer PKs) |

### Wagtail Support

Wagtail CMS works fully with the Couchbase backend. See the [live demo](https://django-couchbase-orm-production.up.railway.app/admin/) for a working example.

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

- **Transactions**: Couchbase ACID transactions require multi-node clusters. `atomic()` runs as a no-op on single-node setups.
- **Window functions**: N1QL doesn't support `OVER()` clauses.
- **Page moves**: Wagtail page tree moves use raw SQL with reserved words. Use delete + recreate as a workaround.
- **Correlated subqueries with GROUP BY**: Some complex query patterns return empty results gracefully instead of crashing.
- **Multi-table inheritance**: Works but may have performance implications with N1QL JOINs.

## Tests

**928+ tests** across 38 test modules, tested on Python 3.10 - 3.13.

| Suite | Tests | What's Covered |
|-------|------:|----------------|
| Document API | 784 | Fields, QuerySet, Manager, Document CRUD, signals, pagination, migrations, auth, sessions |
| Backend Phase 1 | 57 | Connection, cursor, CRUD, admin login, content types |
| Backend Phase 2 | 37 | FK JOINs, M2M, annotate, lookups, F/Q expressions |
| Backend Phase 3 | 23 | Django admin, auth permissions, forms, sessions |
| Backend Phase 4 | 18 | Migrations, schema ops, custom models |
| Backend Phase 5 | 21 | Shared connections, subqueries, bulk ops, edge cases |
| Security | 27 | Injection prevention, password isolation, backtick escaping |
| Wagtail CRUD | 28 | Page create, publish, edit, unpublish, delete, revisions |

**Overall: 91%+ unit test coverage, 0 known vulnerabilities (pip-audit clean).**

```bash
# All tests (requires local Couchbase)
CB_BUCKET=testbucket pytest tests/ -p no:django --ignore=tests/test_wagtail_urls.py

# Document API tests only (no Couchbase required)
pytest tests/ -m "not integration" -p no:django

# Coverage
coverage run -m pytest tests/ && coverage report --show-missing --include="src/*"
```

## Example Project

The [`example/`](example/) directory contains a complete Django + Wagtail + DRF project (BrewSync) deployed at the [live demo](https://django-couchbase-orm-production.up.railway.app). It includes:

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

## License

Apache 2.0
