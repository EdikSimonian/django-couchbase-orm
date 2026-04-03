# Document API

The Document API provides Couchbase-native patterns for when you need direct control over document operations, sub-document mutations, or KV fast-path performance.

## Setup

```python
# settings.py
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "mybucket",
        "SCOPE": "_default",  # optional
    }
}
```

If you're already using the [database backend](database-backend.md), you don't need to set `COUCHBASE` — it's auto-derived from `DATABASES`.

## Defining Documents

```python
from django_couchbase_orm import (
    Document, StringField, IntegerField, FloatField,
    BooleanField, DateTimeField, ListField, DictField,
    EmbeddedDocument, EmbeddedDocumentField, ReferenceField,
)

class Brewery(Document):
    name = StringField(required=True, max_length=200)
    city = StringField()
    state = StringField()
    country = StringField(default="United States")
    founded = IntegerField()

    class Meta:
        collection_name = "breweries"

class Beer(Document):
    name = StringField(required=True)
    abv = FloatField(min_value=0, max_value=100)
    style = StringField()
    brewery = ReferenceField(Brewery)
    active = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        collection_name = "beers"
        indexes = [
            {"fields": ["style"]},
            {"fields": ["abv"]},
        ]
```

## CRUD Operations

### Create

```python
brewery = Brewery(name="My Brewery", city="Portland", state="OR")
brewery.save()
print(brewery.pk)  # Auto-generated document key

# Or use the manager
brewery = Brewery.objects.create(name="My Brewery", city="Portland")
```

### Read

```python
# By primary key (fast KV lookup, ~1ms)
brewery = Brewery.objects.get(pk="brewery-key")

# By field value (N1QL query, ~10-50ms)
brewery = Brewery.objects.get(name="My Brewery")

# First match
brewery = Brewery.objects.filter(city="Portland").first()
```

### Update

```python
brewery.city = "Seattle"
brewery.save()

# Bulk update
Brewery.objects.filter(state="OR").update(country="United States")
```

### Delete

```python
brewery.delete()

# Bulk delete
Brewery.objects.filter(active=False).delete()
```

### Get or Create

```python
brewery, created = Brewery.objects.get_or_create(
    name="My Brewery",
    defaults={"city": "Portland", "state": "OR"},
)
```

## QuerySet

The QuerySet API mirrors Django's:

```python
# Filtering
Brewery.objects.filter(country="United States")
Brewery.objects.filter(name__icontains="brew")
Brewery.objects.filter(founded__gte=2000)
Beer.objects.filter(abv__between=[5.0, 8.0])
Beer.objects.filter(style__in=["IPA", "Stout", "Pale Ale"])

# Exclude
Beer.objects.exclude(active=False)

# Q objects
from django_couchbase_orm.queryset.q import Q
Beer.objects.filter(Q(style="IPA") | Q(style="Pale Ale"))
Beer.objects.filter(Q(abv__gte=7) & ~Q(name__contains="Light"))

# Ordering
Brewery.objects.order_by("name")      # ASC
Brewery.objects.order_by("-founded")   # DESC

# Slicing
Brewery.objects.all()[:10]            # LIMIT 10
Brewery.objects.all()[20:30]          # OFFSET 20 LIMIT 10

# Counting
Beer.objects.filter(style="IPA").count()
Beer.objects.filter(abv__gte=10).exists()

# Values (dicts instead of documents)
Brewery.objects.values("name", "city")[:5]

# Aggregation
from django_couchbase_orm import Avg, Count, Max, Min, Sum
Beer.objects.aggregate(
    avg_abv=Avg("abv"),
    max_abv=Max("abv"),
    total=Count("*"),
)
```

### Lookup Reference

| Lookup | N1QL | Example |
|--------|------|---------|
| `exact` | `= $1` | `name="Alice"` |
| `ne` | `!= $1` | `status__ne="deleted"` |
| `gt` / `gte` | `> $1` / `>= $1` | `age__gte=18` |
| `lt` / `lte` | `< $1` / `<= $1` | `age__lt=65` |
| `in` | `IN $1` | `status__in=["active", "pending"]` |
| `contains` | `CONTAINS()` | `name__contains="brew"` |
| `icontains` | `CONTAINS(LOWER())` | `name__icontains="IPA"` |
| `startswith` | `LIKE 'x%'` | `name__startswith="21st"` |
| `endswith` | `LIKE '%x'` | `name__endswith="IPA"` |
| `iexact` | `LOWER() = LOWER()` | `name__iexact="alice"` |
| `isnull` | `IS NULL` | `email__isnull=True` |
| `regex` | `REGEXP_CONTAINS()` | `name__regex="^[A-Z]"` |
| `between` | `BETWEEN $1 AND $2` | `abv__between=[5, 8]` |

## Fields

### Simple Fields

```python
name = StringField(required=True, max_length=200, min_length=1)
age = IntegerField(min_value=0, max_value=150)
price = FloatField(min_value=0)
active = BooleanField(default=True)
id = UUIDField(auto=True)  # Auto-generates UUID
```

### DateTime Fields

```python
created_at = DateTimeField(auto_now_add=True)  # Set on creation
updated_at = DateTimeField(auto_now=True)       # Set on every save
birthday = DateField()
```

### Compound Fields

```python
tags = ListField(field=StringField())           # ["hoppy", "citrus"]
metadata = DictField()                           # {"key": "value"}
```

### Embedded Documents

Structured nested objects stored within the parent document:

```python
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
    address=Address(city="Portland", state="OR"),
)
company.save()
```

### Reference Fields

Cross-document references (similar to ForeignKey):

```python
class Beer(Document):
    name = StringField(required=True)
    brewery = ReferenceField(Brewery)

beer = Beer(name="IPA", brewery=brewery)  # Stores brewery.pk
beer.save()

# Prefetch to avoid N+1 queries
beers = Beer.objects.select_related("brewery").filter(abv__gte=7)
for beer in beers:
    print(beer._prefetched["brewery"].name)
```

### Field Options

All fields support:

| Option | Description |
|--------|-------------|
| `required` | Field must have a value (default: `False`) |
| `default` | Default value or callable |
| `choices` | List of allowed values |
| `db_field` | Override the JSON key name |
| `validators` | List of validation functions |
| `help_text` | Description for documentation |

## Sub-Document Operations

Read or write specific fields without fetching the entire document:

```python
brewery = Brewery.objects.get(pk="my-brewery")

# Read a field
city = brewery.subdoc.get("city")

# Write a field
brewery.subdoc.upsert("city", "Seattle")

# Nested field access
brewery.subdoc.upsert("address.city", "Seattle")

# Array operations
brewery.subdoc.array_append("tags", "craft")
brewery.subdoc.array_addunique("tags", "organic")

# Atomic counter
brewery.subdoc.increment("visit_count", 1)

# Remove a field
brewery.subdoc.remove("deprecated_field")

# Multiple operations atomically
import couchbase.subdocument as SD
brewery.subdoc.multi_mutate(
    SD.upsert("name", "New Name"),
    SD.increment("version", 1),
    SD.array_append("history", "renamed"),
)
```

## Signals

Django-style signals for document lifecycle events:

```python
from django_couchbase_orm.signals import pre_save, post_save, pre_delete, post_delete

def on_brewery_save(sender, instance, created, **kwargs):
    if created:
        print(f"New brewery: {instance.name}")

post_save.connect(on_brewery_save, sender=Brewery)

# Cascade delete via signals
def delete_beers(sender, instance, **kwargs):
    Beer.objects.filter(brewery=instance.pk).delete()

pre_delete.connect(delete_beers, sender=Brewery)
```

## Pagination

```python
from django_couchbase_orm import CouchbasePaginator

paginator = CouchbasePaginator(Beer.objects.filter(abv__gte=5), per_page=20)
page = paginator.page(1)

for beer in page:
    print(beer.name)

page.has_next         # True
page.has_previous     # False
paginator.num_pages   # 15
paginator.count       # 300
```

## Bulk Operations

```python
# Create many documents
beers = [Beer(name=f"Beer {i}", abv=5.0 + i * 0.1) for i in range(100)]
Beer.objects.bulk_create(beers)

# Update specific fields
for beer in beers:
    beer._data["abv"] = 7.0
Beer.objects.bulk_update(beers, ["abv"])
```

## Async Support

All CRUD and query operations have async variants:

```python
# Async CRUD
brewery = Brewery(name="Async Brewery")
await brewery.asave()
await brewery.areload()
await brewery.adelete()

# Async queries
count = await Brewery.objects.acount()
first = await Brewery.objects.afirst()
beer = await Beer.objects.aget(pk="beer-id")
beers = await Beer.objects.filter(style="IPA").alist()

# Async iteration
async for beer in Beer.objects.filter(abv__gte=7):
    print(beer.name)

# Concurrent queries
import asyncio
count, beers, styles = await asyncio.gather(
    qs.acount(),
    qs[:20].alist(),
    Beer.objects.values("style").alist(),
)
```

Requires ASGI server (uvicorn):
```bash
pip install uvicorn
uvicorn myproject.asgi:application
```

## Migrations

The Document API has its own migration framework, separate from Django's `makemigrations`/`migrate`:

```bash
python manage.py cb_makemigrations   # Auto-detect changes
python manage.py cb_migrate          # Apply migrations
python manage.py cb_migrate --list   # Show status
```

Migration files live in `<app>/cb_migrations/`:

```python
from django_couchbase_orm.migrations import Migration
from django_couchbase_orm.migrations.operations import (
    CreateCollection, CreateIndex, AddField, RunPython,
)

class Migration(Migration):
    app_label = "myapp"
    dependencies = []
    operations = [
        CreateCollection("beers", scope_name="brewing"),
        CreateIndex("idx_style", fields=["style"], collection_name="beers"),
        AddField("beer", "rating", default=0, collection_name="beers"),
    ]
```

### Available Operations

| Operation | Reversible | Description |
|-----------|:----------:|-------------|
| `CreateScope` | Yes | Create a Couchbase scope |
| `DropScope` | No | Drop a scope |
| `CreateCollection` | Yes | Create a collection |
| `DropCollection` | No | Drop a collection |
| `CreateIndex` | Yes | Create a N1QL index |
| `DropIndex` | No | Drop an index |
| `AddField` | Yes | Add field with default to all docs |
| `RemoveField` | No | Remove a field |
| `RenameField` | Yes | Rename a field |
| `AlterField` | No | Transform values via N1QL |
| `RunN1QL` | Optional | Execute raw N1QL |
| `RunPython` | Optional | Execute Python callable |

## Management Commands

```bash
python manage.py cb_ensure_indexes           # Create indexes from Meta
python manage.py cb_ensure_indexes --primary  # Also create primary indexes
python manage.py cb_create_collections       # Create collections for all Documents
```

## Document Meta Options

```python
class MyDocument(Document):
    class Meta:
        collection_name = "my_collection"  # Default: lowercase class name
        scope_name = "_default"
        bucket_alias = "default"           # Key in COUCHBASE settings
        doc_type_field = "_type"           # Type discriminator field
        abstract = True                    # Inheritance only, not stored
        indexes = [
            {"fields": ["name"]},
            {"fields": ["created_at", "status"]},
        ]
```

## Multiple Connections

```python
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://cluster1",
        "USERNAME": "user1",
        "PASSWORD": "pass1",
        "BUCKET": "app_data",
    },
    "analytics": {
        "CONNECTION_STRING": "couchbase://cluster2",
        "USERNAME": "user2",
        "PASSWORD": "pass2",
        "BUCKET": "analytics",
    },
}

class Event(Document):
    class Meta:
        bucket_alias = "analytics"  # Uses the analytics connection
```

## Session Backend

Store Django sessions in Couchbase with automatic TTL expiry:

```python
SESSION_ENGINE = "django_couchbase_orm.contrib.sessions.backend"
```

## Auth Backend

Authenticate users against Couchbase-stored documents:

```python
AUTHENTICATION_BACKENDS = [
    "django_couchbase_orm.contrib.auth.backend.CouchbaseAuthBackend",
]
```

```python
from django_couchbase_orm.contrib.auth.models import User

user = User.create_user("alice", "alice@example.com", "password")
admin = User.create_superuser("admin", "admin@example.com", "admin")

user.check_password("password")  # True
user.set_password("new_password")
```
