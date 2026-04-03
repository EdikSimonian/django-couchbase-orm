# Hybrid Architecture

You can use both the Django Database Backend and the Document API in the same project. This gives you the best of both worlds.

## When to Use Which

| Use Case | Approach |
|----------|----------|
| CMS pages, admin-managed content | Database Backend (`django.db.models.Model`) |
| User accounts, permissions, groups | Database Backend |
| Forms, DRF APIs, third-party Django apps | Database Backend |
| High-throughput event ingestion | Document API |
| Real-time counters, analytics | Document API (subdoc ops) |
| Schemaless/flexible data | Document API |
| Couchbase-specific features (subdoc, KV) | Document API |

## Setup

```python
# settings.py

# Database Backend — for Django models
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

# Document API config is auto-derived from DATABASES.
# No need to set COUCHBASE separately.
```

## Example: CMS + Analytics

```python
# models.py — Django models for CMS content
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    published = models.BooleanField(default=False)


# documents.py — Document API for analytics
from django_couchbase_orm import Document, StringField, IntegerField, DateTimeField

class PageView(Document):
    url = StringField(required=True)
    user_agent = StringField()
    ip_address = StringField()
    timestamp = DateTimeField(auto_now_add=True)

    class Meta:
        collection_name = "page_views"

    def track(self):
        """Fast KV write — no N1QL overhead."""
        self.save()


# views.py — Using both together
from django.views import View
from django.http import JsonResponse

class ArticleView(View):
    def get(self, request, pk):
        # Django ORM for the article (admin, permissions, etc.)
        article = Article.objects.select_related("author").get(pk=pk)

        # Document API for analytics (fast KV write)
        PageView(url=request.path, user_agent=request.META.get("HTTP_USER_AGENT", "")).save()

        # Document API for real-time counter (subdoc atomic increment)
        from django_couchbase_orm.connection import get_collection
        coll = get_collection(collection="article_stats")
        try:
            coll.binary().increment(f"views:{pk}")
        except:
            pass

        return JsonResponse({"title": article.title, "author": article.author.username})
```

## Shared Connection

Both APIs share the same Couchbase cluster connection. When the database backend connects, it automatically shares its cluster instance with the Document API:

```python
from django.db import connection
from django_couchbase_orm.connection import get_cluster

# Same cluster object — no duplicate connections
assert get_cluster() is connection.couchbase_cluster
```

This happens automatically — no configuration needed.

## Data Access Across APIs

Data written by one API is immediately visible to the other:

```python
# Write via Django Model
from django.contrib.auth.models import User
user = User.objects.create_user("alice", "alice@example.com", "password")

# Read the same data via Document API (raw N1QL)
from django_couchbase_orm.connection import get_cluster
cluster = get_cluster()
result = cluster.query(
    "SELECT * FROM `mybucket`.`_default`.`auth_user` WHERE `username` = $1",
    positional_parameters=["alice"],
)
```

## Performance Comparison

| Operation | Database Backend | Document API |
|-----------|-----------------|--------------|
| Get by PK | ~10-50ms (N1QL) | ~1ms (KV) |
| Filter query | ~10-100ms (N1QL) | ~10-100ms (N1QL) |
| Insert | ~5-20ms (N1QL UPSERT) | ~1-5ms (KV) |
| Subdoc update | Not available | ~1ms (KV) |
| Bulk insert (100 docs) | ~50-200ms | ~10-50ms |
| Admin/forms/DRF | Built-in | Needs adapters |

The Document API is faster for single-document operations because it uses Couchbase's KV service directly, bypassing the N1QL query engine.
