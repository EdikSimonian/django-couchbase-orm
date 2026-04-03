# Django Database Backend

Use Couchbase as a drop-in replacement for PostgreSQL, MySQL, or SQLite. Standard `django.db.models.Model` classes work transparently.

## Setup

```python
# settings.py
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "mybucket",           # Couchbase bucket name
        "USER": "Administrator",       # Couchbase username
        "PASSWORD": "password",        # Couchbase password
        "HOST": "couchbase://localhost", # Connection string
        "OPTIONS": {
            "SCOPE": "_default",       # Couchbase scope (optional)
        },
    }
}

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"
```

The `CouchbaseAutoField` generates sequential integer primary keys using Couchbase atomic counters, just like SQL auto-increment.

## How It Works

### Collections = Tables

Each Django model maps to a Couchbase collection. When you run `manage.py migrate`, collections are created automatically.

```
Django Model          →  Couchbase Collection
─────────────────────────────────────────────
auth_user             →  testbucket._default.auth_user
auth_group            →  testbucket._default.auth_group
myapp_article         →  testbucket._default.myapp_article
```

### Documents = Rows

Each model instance is stored as a JSON document in Couchbase. The document key is the string representation of the integer primary key.

```python
# Django model
class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    published = models.BooleanField(default=False)
```

```json
// Stored in Couchbase as document key "42"
{
    "id": 42,
    "title": "Hello World",
    "body": "This is my first article.",
    "published": true
}
```

### N1QL = SQL

Django's ORM queries are translated to N1QL (Couchbase's SQL-like query language).

```python
Article.objects.filter(published=True).order_by('-id')[:10]
```

Becomes:

```sql
SELECT `myapp_article`.`id`, `myapp_article`.`title`, ...
FROM `mybucket`.`_default`.`myapp_article`
WHERE `myapp_article`.`published` = true
ORDER BY `myapp_article`.`id` DESC
LIMIT 10
```

## Models

Standard Django models work without modification:

```python
from django.db import models

class Author(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(default="")
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    tags = models.ManyToManyField("Tag", blank=True)
    published = models.BooleanField(default=False)
    views = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
```

## Supported Field Types

All standard Django field types work:

| Field | Stored As | Notes |
|-------|-----------|-------|
| `CharField` | string | |
| `TextField` | string | |
| `IntegerField` | number | All integer variants supported |
| `FloatField` | number | |
| `DecimalField` | number | Stored as float |
| `BooleanField` | boolean | |
| `DateField` | string | ISO 8601 format |
| `DateTimeField` | string | ISO 8601 format, auto_now/auto_now_add work |
| `TimeField` | string | ISO 8601 format |
| `UUIDField` | string | |
| `JSONField` | native JSON | Couchbase is JSON-native |
| `FileField` | string | Stores file path, actual files in Django storage |
| `ImageField` | string | Same as FileField |
| `ForeignKey` | number | Stores the referenced document's PK |
| `ManyToManyField` | junction collection | Auto-created through table |

## Relationships

### ForeignKey

ForeignKey fields store the referenced document's primary key. JOINs use N1QL ANSI JOIN syntax.

```python
# Filter across FK
Article.objects.filter(author__name="Alice")

# Generated N1QL:
# SELECT ... FROM myapp_article
# INNER JOIN myapp_author ON (myapp_article.author_id = myapp_author.id)
# WHERE myapp_author.name = 'Alice'
```

### select_related

Loads related objects in a single query using JOINs:

```python
articles = Article.objects.select_related("author").all()
for article in articles:
    print(article.author.name)  # No extra query
```

### prefetch_related

Loads related objects in a separate batch query:

```python
articles = Article.objects.prefetch_related("tags").all()
for article in articles:
    print(article.tags.all())  # Pre-loaded, no extra query
```

### ManyToManyField

M2M relationships use a junction collection (like SQL junction tables):

```python
article = Article.objects.get(pk=1)
tag = Tag.objects.get(name="python")

article.tags.add(tag)
article.tags.remove(tag)
article.tags.clear()
article.tags.set([tag1, tag2])

# Filter through M2M
Article.objects.filter(tags__name="python")
```

## QuerySet API

The full Django QuerySet API is supported:

```python
# Filtering
Article.objects.filter(published=True)
Article.objects.filter(title__icontains="django")
Article.objects.filter(views__gte=100)
Article.objects.filter(author__name__startswith="A")
Article.objects.exclude(published=False)

# Q objects
from django.db.models import Q
Article.objects.filter(Q(published=True) | Q(views__gte=1000))
Article.objects.filter(~Q(title__contains="draft"))

# F expressions
from django.db.models import F
Article.objects.filter(views__gte=F("views"))  # Self-referencing
Article.objects.update(views=F("views") + 1)   # Atomic increment

# Aggregation
from django.db.models import Count, Avg, Max
Article.objects.aggregate(
    total=Count("id"),
    avg_views=Avg("views"),
    max_views=Max("views"),
)

# Annotation
Author.objects.annotate(
    article_count=Count("article")
).filter(article_count__gt=5)

# Values
Article.objects.values("title", "author__name")
Article.objects.values_list("title", flat=True)

# Ordering, slicing
Article.objects.order_by("-created_at")[:20]
Article.objects.all()[10:20]  # OFFSET 10 LIMIT 10

# Distinct, only, defer
Article.objects.values("author_id").distinct()
Article.objects.only("title", "published")
Article.objects.defer("body")

# Bulk operations
Article.objects.bulk_create([Article(title=f"Post {i}") for i in range(100)])
Article.objects.filter(published=False).update(published=True)
Article.objects.filter(views=0).delete()
```

## Migrations

Standard Django migrations work:

```bash
python manage.py makemigrations
python manage.py migrate
```

`CreateModel` creates a Couchbase collection + primary index. `AddField` is a no-op (Couchbase is schemaless). `AddIndex` creates a N1QL secondary index.

## Django Admin

The admin interface works out of the box:

```python
# admin.py
from django.contrib import admin
from .models import Article, Author

admin.site.register(Article)
admin.site.register(Author)
```

List views, add/edit forms, search, filtering, ordering, and delete all work.

## Django Auth

The full auth system works — users, groups, permissions:

```bash
python manage.py createsuperuser
```

```python
from django.contrib.auth.models import User

user = User.objects.create_user("alice", "alice@example.com", "password")
user.has_perm("myapp.add_article")  # Permission checking works

# Groups and permissions
from django.contrib.auth.models import Group, Permission
editors = Group.objects.create(name="Editors")
perm = Permission.objects.get(codename="change_article")
editors.permissions.add(perm)
user.groups.add(editors)
```

## Django REST Framework

DRF serializers work automatically:

```python
from rest_framework import serializers, viewsets
from .models import Article

class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = "__all__"

class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
```

## ModelForms

Standard Django forms work:

```python
from django import forms
from .models import Article

class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "body", "published"]
```

## Sessions

Django's database session backend works with Couchbase:

```python
SESSION_ENGINE = "django.contrib.sessions.backends.db"
```

## ContentTypes

The `ContentType` framework works, enabling generic relations and Django admin history.

## Wagtail CMS

See [Wagtail Integration](wagtail.md) for details on running Wagtail with Couchbase.

## Limitations

| Feature | Status | Notes |
|---------|--------|-------|
| Transactions | No-op | Couchbase ACID needs multi-node cluster |
| Savepoints | Not supported | |
| Window functions (OVER) | Not supported | N1QL limitation |
| Multi-table inheritance | Works | Performance may vary with JOINs |
| Raw SQL | Use N1QL syntax | Not PostgreSQL/MySQL SQL |
| Database-level UNIQUE | Via N1QL index | Not enforced like SQL constraints |
| Correlated subquery + GROUP BY | Graceful empty | N1QL is stricter than SQL |

## Architecture

```
Django ORM
    ↓
SQLCompiler → N1QL Compiler (translates SQL AST to N1QL)
    ↓
CouchbaseCursor (DB-API 2.0 interface)
    ↓
Couchbase Python SDK → cluster.query(n1ql)
    ↓
Couchbase Server (N1QL query service)
```

Key components:
- **`compiler.py`** — Translates Django's SQL AST to N1QL statements
- **`cursor.py`** — DB-API 2.0 cursor with %s→$N param conversion, IN clause collapsing, column deduplication
- **`schema.py`** — Creates/drops collections and indexes
- **`operations.py`** — Date functions, quoting, type adaptation
- **`fields.py`** — CouchbaseAutoField with atomic counter PKs
