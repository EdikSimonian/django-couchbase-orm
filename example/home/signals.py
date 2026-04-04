"""Embed title and slug into BlogPage documents for mobile sync."""
from django.db import connection


def embed_blog_title(sender, instance, **kwargs):
    """After a BlogPage is published, copy title+slug into home_blogpage doc."""
    from home.models import BlogPage
    if not isinstance(instance.specific, BlogPage):
        return
    try:
        cursor = connection.cursor()
        # Raw N1QL with inline values (safe — title/slug are from our own Wagtail data)
        title = instance.title.replace("'", "''")
        slug = instance.slug.replace("'", "''")
        pk = int(instance.pk)
        sql = (
            f"UPDATE `beer-sample`.`_default`.`home_blogpage` "
            f"SET title = '{title}', slug = '{slug}' "
            f"WHERE page_ptr_id = {pk}"
        )
        cursor.execute(sql)
        print(f"[Signal] Embedded title '{instance.title}' into blogpage {pk}")
    except Exception as e:
        print(f"[Signal] Failed to embed blog title: {e}")
