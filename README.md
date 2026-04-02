# django-couchbase-orm

A Django-style ORM for Couchbase. Define models, run queries, and manage documents using familiar Django patterns with Couchbase Server as the backend.

**Live Demo:** [django-couchbase-orm-production.up.railway.app](https://django-couchbase-orm-production.up.railway.app) | **PyPI:** [django-couchbase-orm](https://pypi.org/project/django-couchbase-orm/)

Works **alongside** Django's built-in ORM — use `django.db.models.Model` for relational data and `django_couchbase_orm.Document` for Couchbase data in the same project. Or go fully Couchbase with the included session and auth backends.

## Features

- Declarative document models with typed fields
- Django-style QuerySet with filtering, ordering, slicing, and Q objects
- N1QL query builder with parameterized queries (injection-safe)
- KV-optimized `get(pk=...)` for fast single-document lookups
- Sub-document operations (partial reads/writes)
- Signals: `pre_save`, `post_save`, `pre_delete`, `post_delete`
- Couchbase session backend (TTL-based expiry)
- Couchbase auth backend (User model, authentication)
- Embedded documents, references, compound fields
- Auto-timestamps (`auto_now`, `auto_now_add`)
- Aggregation: `Count`, `Sum`, `Avg`, `Min`, `Max`
- `select_related()` for ReferenceField prefetching
- `CouchbasePaginator` with Django-style Page objects
- `bulk_create()` and `bulk_update()` for batch operations
- Management commands: `cb_ensure_indexes`, `cb_create_collections`

## Requirements

- Python 3.10+
- Django 4.2+
- Couchbase Python SDK 4.1+

## Installation

```bash
pip install django-couchbase-orm
```

## Quick Start

### 1. Configure Django settings

```python
# settings.py
INSTALLED_APPS = [
    ...
    "django_couchbase_orm",
]

COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbases://your-cluster.cloud.couchbase.com",
        "USERNAME": "your-user",
        "PASSWORD": "your-password",
        "BUCKET": "your-bucket",
        "SCOPE": "_default",  # optional, defaults to _default
    }
}
```

### 2. Define documents

```python
from django_couchbase_orm import Document, StringField, IntegerField, FloatField, BooleanField, DateTimeField

class Brewery(Document):
    name = StringField(required=True)
    city = StringField()
    state = StringField()
    country = StringField()
    description = StringField()

    class Meta:
        collection_name = "_default"
        doc_type_field = "type"  # field name for type discriminator

class Beer(Document):
    name = StringField(required=True)
    abv = FloatField()
    style = StringField()
    brewery_id = StringField()

    class Meta:
        collection_name = "_default"
        doc_type_field = "type"
```

### 3. Use it

```python
# Create
brewery = Brewery(name="My Brewery", city="Portland", country="United States")
brewery.save()

# Get by primary key (fast KV lookup)
brewery = Brewery.objects.get(pk="my_brewery_id")

# Query with Django-style filtering
us_breweries = Brewery.objects.filter(country="United States").order_by("name")[:20]
ipa_beers = Beer.objects.filter(style__icontains="ipa", abv__gte=6.0)
count = Beer.objects.filter(brewery_id="my_brewery").count()

# Update
brewery.city = "Seattle"
brewery.save()

# Delete
brewery.delete()
```

## Fields

| Field | Python Type | Notes |
|-------|-------------|-------|
| `StringField` | `str` | `min_length`, `max_length`, `regex` |
| `IntegerField` | `int` | `min_value`, `max_value` |
| `FloatField` | `float` | `min_value`, `max_value` |
| `BooleanField` | `bool` | |
| `UUIDField` | `uuid.UUID` | `auto=True` to auto-generate |
| `DateTimeField` | `datetime` | `auto_now`, `auto_now_add`; stored as ISO 8601 |
| `DateField` | `date` | `auto_now`, `auto_now_add` |
| `ListField` | `list` | Optional `field` arg for typed elements |
| `DictField` | `dict` | Arbitrary JSON objects |
| `EmbeddedDocumentField` | nested object | Structured sub-documents |
| `ReferenceField` | `str` (key) | Cross-document references |

All fields support: `required`, `default`, `choices`, `db_field`, `validators`.

## QuerySet API

```python
# Filtering
Brewery.objects.filter(country="United States")
Brewery.objects.filter(name__icontains="brew")
Brewery.objects.filter(name__startswith="21st")
Beer.objects.filter(abv__gte=5.0, abv__lte=8.0)
Beer.objects.filter(style__in=["IPA", "Pale Ale"])
Beer.objects.filter(description__isnull=False)
Beer.objects.filter(name__regex="^[A-Z].*IPA$")

# Exclude
Beer.objects.exclude(abv__lt=4.0)

# Q objects for complex queries
from django_couchbase_orm import Q
Beer.objects.filter(Q(style="IPA") | Q(style="Pale Ale"))
Beer.objects.filter(Q(abv__gte=7) & ~Q(name__contains="Light"))

# Ordering
Brewery.objects.order_by("name")       # ascending
Brewery.objects.order_by("-abv")       # descending

# Slicing (LIMIT/OFFSET)
Brewery.objects.all()[:10]             # first 10
Brewery.objects.all()[20:30]           # page 2

# Aggregation
Brewery.objects.filter(country="US").count()
Beer.objects.filter(style="IPA").exists()

# Single objects
Beer.objects.first()
Beer.objects.get(name="21A IPA", brewery_id="21st_amendment_brewery_cafe")

# Values (return dicts instead of documents)
Brewery.objects.values("name", "city")[:5]

# Raw N1QL
Beer.objects.raw("SELECT * FROM `bucket`.`scope`.`coll` WHERE type = $1", ["beer"])

# Iterator (memory-efficient for large result sets)
for beer in Beer.objects.filter(abv__gte=10).iterator():
    print(beer.name)
```

### Lookup Reference

| Lookup | N1QL | Example |
|--------|------|---------|
| `exact` (default) | `= $1` | `name="Alice"` |
| `ne` | `!= $1` | `status__ne="deleted"` |
| `gt` / `gte` | `> $1` / `>= $1` | `age__gte=18` |
| `lt` / `lte` | `< $1` / `<= $1` | `age__lt=65` |
| `in` | `IN $1` | `status__in=["active", "pending"]` |
| `contains` | `CONTAINS()` | `name__contains="brew"` |
| `icontains` | `CONTAINS(LOWER())` | `name__icontains="IPA"` |
| `startswith` / `istartswith` | `LIKE 'x%'` | `name__startswith="21st"` |
| `endswith` / `iendswith` | `LIKE '%x'` | `name__endswith="IPA"` |
| `iexact` | `LOWER() = LOWER()` | `name__iexact="alice"` |
| `isnull` | `IS NULL` / `IS NOT NULL` | `email__isnull=True` |
| `regex` / `iregex` | `REGEXP_CONTAINS()` | `name__regex="^[A-Z]"` |
| `between` | `BETWEEN $1 AND $2` | `abv__between=[5, 8]` |

## Embedded Documents

```python
from django_couchbase_orm import EmbeddedDocument, EmbeddedDocumentField, StringField

class Address(EmbeddedDocument):
    street = StringField()
    city = StringField(required=True)
    state = StringField()
    zip_code = StringField(db_field="zipCode")

class Company(Document):
    name = StringField(required=True)
    address = EmbeddedDocumentField(Address)

company = Company(
    name="Acme",
    address=Address(city="Portland", state="OR", zip_code="97201"),
)
company.save()
```

## Sub-Document Operations

Partial reads and writes without fetching the full document:

```python
brewery = Brewery.objects.get(pk="my_brewery")

# Read a nested field
city = brewery.subdoc.get("address.city")

# Write a nested field
brewery.subdoc.upsert("address.city", "Seattle")

# Array operations
brewery.subdoc.array_append("tags", "craft")
brewery.subdoc.array_addunique("tags", "organic")

# Counters
brewery.subdoc.increment("visit_count", 1)

# Multiple operations in one call
import couchbase.subdocument as SD
brewery.subdoc.multi_mutate(
    SD.upsert("name", "New Name"),
    SD.increment("version", 1),
)
```

## Signals

```python
from django_couchbase_orm.signals import pre_save, post_save, pre_delete, post_delete

def on_brewery_save(sender, instance, created, **kwargs):
    if created:
        print(f"New brewery: {instance.name}")

post_save.connect(on_brewery_save, sender=Brewery)
```

## Couchbase Session Backend

Store Django sessions in Couchbase with automatic TTL expiry:

```python
# settings.py
SESSION_ENGINE = "django_couchbase_orm.contrib.sessions.backend"

# Optional: customize session storage location
COUCHBASE_SESSION = {
    "ALIAS": "default",       # which COUCHBASE connection to use
    "COLLECTION": "_default", # collection name
}
```

## Couchbase Auth Backend

Authenticate users against Couchbase-stored User documents:

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    "django_couchbase_orm.contrib.auth.backend.CouchbaseAuthBackend",
]
```

```python
from django_couchbase_orm.contrib.auth.models import User

# Create users
user = User.create_user("alice", "alice@example.com", "secret123")
admin = User.create_superuser("admin", "admin@example.com", "admin123")

# Authenticate
user = backend.authenticate(request, username="alice", password="secret123")

# Password management
user.set_password("new_password")
user.check_password("new_password")  # True
```

## Document Meta Options

```python
class MyDocument(Document):
    class Meta:
        collection_name = "my_collection"  # Couchbase collection (default: class name lowercase)
        scope_name = "_default"            # Couchbase scope
        bucket_alias = "default"           # Key in COUCHBASE settings
        doc_type_field = "_type"           # Type discriminator field name
        abstract = True                    # Don't register, for inheritance only
```

## Multiple Couchbase Connections

```python
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbases://cluster1.example.com",
        "USERNAME": "user1",
        "PASSWORD": "pass1",
        "BUCKET": "app_data",
    },
    "analytics": {
        "CONNECTION_STRING": "couchbases://cluster2.example.com",
        "USERNAME": "user2",
        "PASSWORD": "pass2",
        "BUCKET": "analytics",
    },
}

class Event(Document):
    class Meta:
        bucket_alias = "analytics"
```

## Going Fully Couchbase (No Relational DB)

If you don't use Django admin or permissions, you can drop the relational database entirely:

```python
INSTALLED_APPS = [
    "django_couchbase_orm",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # your apps
]

SESSION_ENGINE = "django_couchbase_orm.contrib.sessions.backend"
AUTHENTICATION_BACKENDS = [
    "django_couchbase_orm.contrib.auth.backend.CouchbaseAuthBackend",
]

# No DATABASES setting needed
```

## Aggregation

```python
from django_couchbase_orm import Avg, Count, Max, Min, Sum

Beer.objects.filter(style="IPA").aggregate(
    avg_abv=Avg("abv"),
    max_abv=Max("abv"),
    total=Count("*"),
)
# Returns: {"avg_abv": 6.5, "max_abv": 12.0, "total": 150}
```

## Pagination

```python
from django_couchbase_orm import CouchbasePaginator

paginator = CouchbasePaginator(Beer.objects.filter(abv__gte=5), per_page=20)
page = paginator.page(1)

for beer in page:
    print(beer.name)

page.has_next        # True
page.has_previous    # False
page.next_page_number  # 2
paginator.num_pages  # 15
paginator.count      # 300
```

## Bulk Operations

```python
# Create many documents at once
beers = [Beer(name=f"Beer {i}", abv=5.0 + i * 0.1) for i in range(100)]
Beer.objects.bulk_create(beers)

# Update specific fields on many documents
for beer in beers:
    beer._data["abv"] = 7.0
Beer.objects.bulk_update(beers, ["abv"])
```

## select_related (Prefetching)

```python
# Avoid N+1 queries when accessing ReferenceFields
beers = Beer.objects.select_related("brewery").filter(abv__gte=7)
for beer in beers:
    # brewery is already prefetched — no extra query
    print(beer._prefetched["brewery"].name)
```

## Management Commands

```bash
# Create N1QL indexes declared in Document Meta.indexes
python manage.py cb_ensure_indexes
python manage.py cb_ensure_indexes --primary    # also create primary indexes
python manage.py cb_ensure_indexes --dry-run    # preview without executing

# Create scopes and collections for all Document classes
python manage.py cb_create_collections
python manage.py cb_create_collections --dry-run
```

## Async Support

Run queries concurrently for faster page loads. Requires ASGI (uvicorn).

```python
import asyncio
from django_couchbase_orm import Document, StringField, FloatField

# Async Document CRUD
brewery = Brewery(name="My Brewery", city="Portland")
await brewery.asave()
await brewery.areload()
await brewery.adelete()

# Async QuerySet methods
count = await Brewery.objects.acount()
first = await Brewery.objects.afirst()
beer = await Beer.objects.aget(pk="beer-id")
exists = await Beer.objects.filter(abv__gte=10).aexists()
beers = await Beer.objects.filter(style="IPA").alist()

# Async Manager
beer = await Beer.objects.aget(pk="beer-id")
new_beer = await Beer.objects.acreate(name="New IPA", abv=7.5)

# Async iteration
async for beer in Beer.objects.filter(abv__gte=7):
    print(beer.name)

# Concurrent queries (the big performance win)
async def beer_list_view(request):
    count, beers, styles = await asyncio.gather(
        qs.acount(),                    # query 1
        qs[:20].alist(),                # query 2
        Beer.objects.values("style").alist(),  # query 3
    )
    # All 3 run concurrently — 3x faster than sequential
```

**ASGI setup:**
```bash
pip install uvicorn
uvicorn myproject.asgi:application --host 0.0.0.0 --port 8000
```

## Performance

Built-in optimizations for production deployments:

- **Connection pre-warming**: Couchbase connections are established in a background thread on app startup, eliminating the 10-15s cold start on the first request
- **Prepared statements**: All N1QL queries use `adhoc=False`, telling Couchbase to cache the query plan for ~30-50% faster repeated queries
- **Async + gather**: Async views can run multiple queries concurrently, making multi-query pages 2-3x faster
- **KV fast path**: `get(pk=...)` bypasses N1QL entirely and uses Couchbase KV operations (~1ms vs ~50ms)

To disable connection pre-warming:
```python
COUCHBASE_PREWARM = False
```

## Security

The library is designed with security as a priority:

| Protection | Details |
|-----------|---------|
| **N1QL injection** | All queries use parameterized values (`$1, $2, ...`) — never string interpolation |
| **Identifier injection** | All field names validated against `^[a-zA-Z_]\w*$` before embedding in queries |
| **Password storage** | Uses Django's `make_password`/`check_password` (PBKDF2/Argon2) |
| **Timing attack prevention** | Auth backend runs password hasher on every code path (constant-time) |
| **Session fixation** | Session key is cycled on login via `request.session.cycle_key()` |
| **Document ID injection** | User-supplied IDs are namespace-prefixed and validated against a character whitelist |
| **CSRF** | All mutation forms include `{% csrf_token %}`, Django middleware enforces it |
| **XSS** | Django template auto-escaping on all output; URL fields validated for `http(s)://` scheme |
| **Credential safety** | All secrets via environment variables; defaults fail in production if not set |
| **Session key redaction** | Session keys never appear in log output |
| **Login rate limiting** | 5 failed attempts triggers a 5-minute lockout (example app) |

## Test Coverage

**501 tests** across 20 test modules, tested on Python 3.10, 3.11, 3.12, and 3.13.

| Module | Coverage |
|--------|----------|
| Fields (base, simple, datetime, compound, reference) | 93-100% |
| Exceptions, signals, utils | 100% |
| Paginator | 100% |
| Auth backend | 100% |
| Q objects | 95% |
| Transform lookups | 99% |
| Options | 98% |
| Document (sync + async) | 80% |
| N1QL query builder | 92% |
| QuerySet (sync + async) | 46%* |
| Manager (sync + async) | 76% |
| Session backend | 74% |
| Management commands | 63-76% |

\* QuerySet execution methods require a live Couchbase cluster. They are tested via live integration tests but not counted in unit test coverage.

**Overall: 80% unit test coverage, 501 tests, 0 known vulnerabilities (pip-audit clean).**

## Development

```bash
git clone https://github.com/EdikSimonian/django-couchbase-orm.git
cd django-couchbase-orm
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Running lint
```bash
ruff check src/
ruff format --check src/
```

### Running coverage
```bash
coverage run -m pytest tests/
coverage report --show-missing --include="src/*"
```

## License

Apache 2.0
