"""Phase 4 tests: Migrations, Transactions, Schema Operations, Custom Models.

Tests the full migration workflow, schema editor operations, transaction
behavior, and custom model CRUD with FK/M2M.
"""

import uuid

import pytest

pytestmark = [
    pytest.mark.phase4,
    pytest.mark.skipif(
        not __import__("tests.test_backend_crud", fromlist=["_couchbase_available"])._couchbase_available(),
        reason="Local Couchbase not available",
    ),
    pytest.mark.django_db(transaction=True),
]


class TestMigrationRecorder:
    """Test Django migration state tracking."""

    def test_applied_migrations(self):
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder

        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        assert len(applied) > 0

    def test_record_and_unapply(self):
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder

        recorder = MigrationRecorder(connection)
        recorder.record_applied("test_phase4", "0001_test")
        assert ("test_phase4", "0001_test") in recorder.applied_migrations()

        recorder.record_unapplied("test_phase4", "0001_test")
        assert ("test_phase4", "0001_test") not in recorder.applied_migrations()

    def test_showmigrations(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("showmigrations", stdout=out)
        output = out.getvalue()
        assert "auth" in output
        assert "[X]" in output


class TestSchemaEditor:
    """Test schema editor operations."""

    def test_create_and_delete_model(self):
        from django.db import connection, models

        class TempModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_schema"
                db_table = "test_schema_temp"

        with connection.schema_editor() as editor:
            editor.create_model(TempModel)

        tables = [t.name for t in connection.introspection.get_table_list(None)]
        assert "test_schema_temp" in tables

        with connection.schema_editor() as editor:
            editor.delete_model(TempModel)

        tables = [t.name for t in connection.introspection.get_table_list(None)]
        assert "test_schema_temp" not in tables

    def test_create_model_with_m2m(self):
        from django.db import connection, models

        class TempA(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_schema"
                db_table = "test_schema_a"

        class TempB(models.Model):
            name = models.CharField(max_length=100)
            a_items = models.ManyToManyField(TempA)

            class Meta:
                app_label = "test_schema"
                db_table = "test_schema_b"

        with connection.schema_editor() as editor:
            editor.create_model(TempA)
            editor.create_model(TempB)

        tables = [t.name for t in connection.introspection.get_table_list(None)]
        assert "test_schema_a" in tables
        assert "test_schema_b" in tables
        assert "test_schema_b_a_items" in tables

        with connection.schema_editor() as editor:
            editor.delete_model(TempB)
            editor.delete_model(TempA)

    def test_add_field(self):
        """Adding a field is a no-op for schemaless Couchbase — just verify no crash."""
        from django.db import connection, models

        class TempField(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_schema"
                db_table = "test_schema_field"

        with connection.schema_editor() as editor:
            editor.create_model(TempField)

        new_field = models.CharField(max_length=200, null=True, default=None)
        new_field.set_attributes_from_name("description")
        with connection.schema_editor() as editor:
            editor.add_field(TempField, new_field)

        with connection.schema_editor() as editor:
            editor.delete_model(TempField)


class TestTransactions:
    """Test transaction behavior."""

    def test_atomic_basic(self):
        """atomic() should not crash."""
        from django.db import transaction
        from django.contrib.auth.models import Group

        name = f"txn_{uuid.uuid4().hex[:6]}"
        with transaction.atomic():
            Group.objects.create(name=name)
        assert Group.objects.filter(name=name).exists()
        Group.objects.filter(name=name).delete()

    def test_atomic_nested(self):
        """Nested atomic() should not crash."""
        from django.db import transaction
        from django.contrib.auth.models import Group

        name = f"txn_n_{uuid.uuid4().hex[:6]}"
        with transaction.atomic():
            with transaction.atomic():
                Group.objects.create(name=name)
        assert Group.objects.filter(name=name).exists()
        Group.objects.filter(name=name).delete()


class TestCustomModel:
    """Test custom model (Article + Tag) with FK, M2M, auto_now."""

    def test_create_article(self):
        from tests.testapp.models import Article

        a = Article.objects.create(title="Test", body="Body")
        assert a.pk is not None
        assert a.created_at is not None
        a.delete()

    def test_article_with_fk(self):
        from tests.testapp.models import Article
        from django.contrib.auth.models import User

        u = User.objects.create_user(f"a_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        a = Article.objects.create(title="FK Test", author=u)
        a.refresh_from_db()
        assert a.author_id == u.pk
        a.delete()
        u.delete()

    def test_article_select_related(self):
        from tests.testapp.models import Article
        from django.contrib.auth.models import User

        u = User.objects.create_user(f"sr_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        Article.objects.create(title="SR Test", author=u)
        articles = list(
            Article.objects.select_related("author").filter(author=u)
        )
        assert len(articles) == 1
        assert articles[0].author.username == u.username
        articles[0].delete()
        u.delete()

    def test_article_m2m_tags(self):
        from tests.testapp.models import Article, Tag

        a = Article.objects.create(title="Tagged")
        t1 = Tag.objects.create(name=f"t1_{uuid.uuid4().hex[:4]}")
        t2 = Tag.objects.create(name=f"t2_{uuid.uuid4().hex[:4]}")
        t1.articles.add(a)
        t2.articles.add(a)

        assert a.tags.count() == 2
        assert t1.articles.count() == 1

        a.delete()
        t1.delete()
        t2.delete()

    def test_article_filter_by_author(self):
        from tests.testapp.models import Article
        from django.contrib.auth.models import User

        u = User.objects.create_user(f"af_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        Article.objects.create(title="A1", author=u)
        Article.objects.create(title="A2", author=u)

        assert Article.objects.filter(author=u).count() == 2
        assert Article.objects.filter(author__username=u.username).count() == 2

        Article.objects.filter(author=u).delete()
        u.delete()

    def test_article_update(self):
        from tests.testapp.models import Article

        a = Article.objects.create(title="Old Title", views=0)
        Article.objects.filter(pk=a.pk).update(title="New Title", views=10)
        a.refresh_from_db()
        assert a.title == "New Title"
        assert a.views == 10
        a.delete()

    def test_article_auto_now(self):
        from tests.testapp.models import Article
        import time

        a = Article.objects.create(title="AutoNow")
        created = a.created_at
        time.sleep(0.1)
        a.title = "Updated"
        a.save()
        a.refresh_from_db()
        # updated_at should be newer than created_at
        assert a.updated_at >= a.created_at
        a.delete()

    def test_article_ordering(self):
        """Meta ordering = ['-created_at'] should apply."""
        from tests.testapp.models import Article
        import time

        a1 = Article.objects.create(title="First")
        time.sleep(0.05)
        a2 = Article.objects.create(title="Second")

        titles = list(Article.objects.filter(
            pk__in=[a1.pk, a2.pk]
        ).values_list("title", flat=True))
        # Default ordering is -created_at, so Second should come first
        assert titles[0] == "Second"
        a1.delete()
        a2.delete()


class TestIntrospection:
    """Test database introspection."""

    def test_get_table_list(self):
        from django.db import connection

        tables = [t.name for t in connection.introspection.get_table_list(None)]
        assert "auth_user" in tables
        assert "django_migrations" in tables
        assert "testapp_article" in tables

    def test_get_table_description(self):
        from django.db import connection

        fields = connection.introspection.get_table_description(None, "auth_user")
        field_names = [f.name for f in fields]
        assert "username" in field_names
        assert "email" in field_names
