# Wagtail CMS Integration

Wagtail works with the Couchbase database backend. Page tree, publishing, admin, images, documents, and custom page types all function correctly.

## Setup

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

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "taggit",
    "modelcluster",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    # Your app
    "home",
]

WAGTAIL_SITE_NAME = "My Site"
```

## First Run

```bash
# Apply all migrations (creates ~50 Couchbase collections)
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Start the server
python manage.py runserver
```

Some Wagtail data migrations may need to be faked on first run (they contain raw SQL for PostgreSQL that doesn't translate to N1QL). The backend handles this gracefully — migrations that fail with N1QL syntax errors return empty results instead of crashing.

## Custom Page Types

```python
# home/models.py
from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel

class HomePage(Page):
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

class BlogPage(Page):
    date = models.DateField("Post date")
    intro = models.CharField(max_length=250)
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("intro"),
        FieldPanel("body"),
    ]
```

```bash
python manage.py makemigrations home
python manage.py migrate home
```

## What Works

| Feature | Status |
|---------|--------|
| Admin dashboard | Works |
| Page explorer (tree view) | Works |
| Create/edit/publish pages | Works |
| Custom page types | Works |
| RichTextField | Works |
| Page tree (TreeBeard) | Works |
| Images admin | Works |
| Documents admin | Works |
| Users/groups admin | Works |
| Sites management | Works |
| Collections | Works |
| Redirects | Works |
| Workflows (basic) | Works |
| Aging pages report | Works |
| Frontend page rendering | Works |
| Page search | Works |
| select_related on pages | Works |
| Specific page types | Works |

## Page Tree

Wagtail uses TreeBeard's materialized path algorithm for the page hierarchy. This works with Couchbase because N1QL supports `LIKE` and `ORDER BY` on path strings.

```python
from wagtail.models import Page

root = Page.objects.get(depth=1)
root.get_children()      # Direct children
root.get_descendants()   # All descendants
page.get_ancestors()     # All ancestors
page.get_parent()        # Direct parent
page.get_siblings()      # Same-level pages

# Add a child page
parent = Page.objects.get(pk=1)
page = HomePage(title="New Page", slug="new-page", body="Hello")
parent.add_child(instance=page)
page.save_revision().publish()
```

## Publishing

```python
page = HomePage.objects.get(slug="my-page")

# Save draft
page.body = "Updated content"
revision = page.save_revision()

# Publish
revision.publish()

# Unpublish
page.unpublish()
```

## Known Limitations

### Gracefully Handled (empty results, no crash)

These N1QL patterns generate warnings but don't break the admin:

- **Correlated subqueries with GROUP BY** — Some Wagtail report queries use patterns that N1QL handles differently from SQL. These return empty results.
- **Tuple IN clauses** — `WHERE (col) IN ((%s), (%s))` patterns are handled by the cursor.

### Data Migrations

Some Wagtail data migrations use raw PostgreSQL SQL (e.g., TreeBeard path calculations). These are automatically faked during `migrate` on fresh installs since they operate on empty collections.

### Content Type IDs

On a fresh install, content type IDs are assigned sequentially by the atomic counter. If you wipe and re-migrate, the IDs will change. In production (single migration), this isn't an issue.

## Example Project

See the [`example/`](../example/) directory for a complete Wagtail + Couchbase project with HomePage and BlogPage models.
