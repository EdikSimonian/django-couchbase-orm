# django-couchbase-orm

[![PyPI](https://img.shields.io/pypi/v/django-couchbase-orm?cacheSeconds=60)](https://pypi.org/project/django-couchbase-orm/)
[![Python](https://img.shields.io/pypi/pyversions/django-couchbase-orm)](https://pypi.org/project/django-couchbase-orm/)
[![License](https://img.shields.io/github/license/EdikSimonian/django-couchbase-orm)](https://github.com/EdikSimonian/django-couchbase-orm/blob/main/LICENSE)

Use Couchbase as your Django database. Drop-in backend for `django.db.models.Model` plus a standalone Document API for Couchbase-native patterns.

**Docs:** [Database Backend](docs/database-backend.md) | [Document API](docs/document-api.md) | [Wagtail](docs/wagtail.md) | [Hybrid Architecture](docs/hybrid.md)

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

### Wagtail Support

Wagtail works with the Couchbase backend:

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
- **Correlated subqueries with GROUP BY**: Some complex query patterns return empty results gracefully instead of crashing.
- **Multi-table inheritance**: Works but may have performance implications with N1QL JOINs.

## Tests

940+ tests covering the database backend and Document API:

```bash
# Document API tests (784 tests)
pytest tests/

# Backend integration tests (156 tests, requires Couchbase)
DJANGO_SETTINGS_MODULE=tests.test_backend_settings pytest tests/test_backend_*.py
```

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
