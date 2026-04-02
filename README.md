# django-cb

A Django-style ORM for Couchbase. Define models, run queries, and manage documents using familiar Django patterns with Couchbase Server as the backend.

**Live Demo:** [django-cb-production.up.railway.app](https://django-cb-production.up.railway.app)

Works **alongside** Django's built-in ORM — use `django.db.models.Model` for relational data and `django_cb.Document` for Couchbase data in the same project. Or go fully Couchbase with the included session and auth backends.

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

## Requirements

- Python 3.10+
- Django 4.2+
- Couchbase Python SDK 4.1+

## Installation

```bash
pip install django-cb
```

## Quick Start

### 1. Configure Django settings

```python
# settings.py
INSTALLED_APPS = [
    ...
    "django_cb",
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
from django_cb import Document, StringField, IntegerField, FloatField, BooleanField, DateTimeField

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
from django_cb import Q
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
from django_cb import EmbeddedDocument, EmbeddedDocumentField, StringField

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
from django_cb.signals import pre_save, post_save, pre_delete, post_delete

def on_brewery_save(sender, instance, created, **kwargs):
    if created:
        print(f"New brewery: {instance.name}")

post_save.connect(on_brewery_save, sender=Brewery)
```

## Couchbase Session Backend

Store Django sessions in Couchbase with automatic TTL expiry:

```python
# settings.py
SESSION_ENGINE = "django_cb.contrib.sessions.backend"

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
    "django_cb.contrib.auth.backend.CouchbaseAuthBackend",
]
```

```python
from django_cb.contrib.auth.models import User

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
    "django_cb",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # your apps
]

SESSION_ENGINE = "django_cb.contrib.sessions.backend"
AUTHENTICATION_BACKENDS = [
    "django_cb.contrib.auth.backend.CouchbaseAuthBackend",
]

# No DATABASES setting needed
```

## Development

```bash
git clone https://github.com/EdikSimonian/django-cb.git
cd django-cb
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0
