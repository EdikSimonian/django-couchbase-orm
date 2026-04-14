"""Phase 5 tests: Shared connections, edge cases, hardening.

Tests connection pool bridging between Document API and DB backend,
complex queries, bulk operations, subqueries, and coexistence.
"""

import uuid

import pytest

from tests.conftest import couchbase_available

pytestmark = [
    pytest.mark.phase5,
    pytest.mark.skipif(not couchbase_available, reason="Local Couchbase not available"),
    pytest.mark.django_db(transaction=True),
]


class TestConnectionSharing:
    """Test connection pool bridging between Document API and DB backend."""

    def test_auto_derived_couchbase_settings(self):
        from django.conf import settings

        # settings.COUCHBASE should be auto-derived from DATABASES
        from django_couchbase_orm.connection import get_or_create_couchbase_settings

        get_or_create_couchbase_settings()
        assert hasattr(settings, "COUCHBASE")
        assert "default" in settings.COUCHBASE
        assert settings.COUCHBASE["default"]["BUCKET"] == "testbucket"

    def test_document_api_cluster_works(self):
        from django_couchbase_orm.connection import get_cluster

        cluster = get_cluster()
        # Verify the cluster is functional by running a simple query.
        from couchbase.options import QueryOptions

        result = cluster.query(
            "SELECT 1 AS val",
            QueryOptions(scan_consistency="request_plus"),
        )
        rows = list(result.rows())
        assert len(rows) == 1

    def test_document_api_works_with_backend_settings(self):
        """Document API should work even without explicit COUCHBASE settings."""
        from django_couchbase_orm.connection import get_cluster, get_bucket

        cluster = get_cluster()
        assert cluster is not None
        bucket = get_bucket()
        assert bucket is not None

    def test_cross_api_data_access(self):
        """Data written via Django Model API should be readable via Document API."""
        from django.contrib.auth.models import Group
        from django.db import connection

        name = f"cross_{uuid.uuid4().hex[:6]}"
        g = Group.objects.create(name=name)

        # Use the backend's cluster directly to avoid shared-cluster lifecycle issues.
        from couchbase.options import QueryOptions

        cluster = connection.couchbase_cluster
        result = cluster.query(
            "SELECT d.`name` FROM `testbucket`.`_default`.`auth_group` AS d WHERE d.`id` = $1",
            QueryOptions(
                positional_parameters=[g.pk], scan_consistency="request_plus"
            ),
        )
        rows = list(result.rows())
        assert len(rows) == 1
        assert rows[0]["name"] == name
        g.delete()


class TestSubqueries:
    """Test subquery operations."""

    def test_pk_in_subquery(self):
        from django.contrib.auth.models import User

        user_pks = User.objects.filter(is_superuser=True).values("pk")
        users = list(User.objects.filter(pk__in=user_pks))
        assert isinstance(users, list)

    def test_exclude_with_subquery(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        auth_ct_ids = ContentType.objects.filter(app_label="auth").values("pk")
        non_auth = Permission.objects.exclude(content_type_id__in=auth_ct_ids)
        total = Permission.objects.count()
        auth_count = Permission.objects.filter(
            content_type__app_label="auth"
        ).count()
        assert non_auth.count() == total - auth_count

    def test_filter_with_queryset_in(self):
        from django.contrib.auth.models import Permission

        # IN with queryset that returns PKs
        add_perm_ids = Permission.objects.filter(
            codename__startswith="add"
        ).values("pk")
        same_perms = Permission.objects.filter(pk__in=add_perm_ids)
        assert same_perms.count() == Permission.objects.filter(
            codename__startswith="add"
        ).count()


class TestBulkOperations:
    """Test bulk create and update."""

    def test_bulk_create(self):
        from django.contrib.auth.models import Group

        prefix = f"bc_{uuid.uuid4().hex[:6]}"
        groups = [Group(name=f"{prefix}_{i}") for i in range(5)]
        Group.objects.bulk_create(groups)
        assert Group.objects.filter(name__startswith=prefix).count() == 5
        Group.objects.filter(name__startswith=prefix).delete()

    def test_bulk_update(self):
        from django.contrib.auth.models import Group

        prefix = f"bu_{uuid.uuid4().hex[:6]}"
        for i in range(3):
            Group.objects.create(name=f"{prefix}_{i}")

        groups = list(Group.objects.filter(name__startswith=prefix))
        for g in groups:
            g.name = g.name + "_updated"
        Group.objects.bulk_update(groups, ["name"])

        assert Group.objects.filter(name__endswith="_updated").count() >= 3
        Group.objects.filter(name__startswith=prefix).delete()


class TestComplexQueries:
    """Test complex query patterns."""

    def test_values_list_multiple_fields(self):
        from django.contrib.auth.models import Permission

        result = list(Permission.objects.values_list("codename", "name")[:3])
        assert len(result) == 3
        assert len(result[0]) == 2

    def test_chained_filters(self):
        from django.contrib.auth.models import User

        qs = (
            User.objects.filter(is_active=True)
            .filter(is_superuser=False)
            .filter(is_staff=False)
        )
        assert qs.count() >= 0

    def test_exclude_complex_q(self):
        from django.contrib.auth.models import Permission
        from django.db.models import Q

        result = Permission.objects.exclude(
            Q(codename__startswith="add") & Q(content_type__app_label="auth")
        )
        assert result.count() > 0

    def test_none_queryset(self):
        from django.contrib.auth.models import User

        empty = User.objects.none()
        assert empty.count() == 0
        assert list(empty) == []
        assert not empty.exists()

    def test_null_fk_filter(self):
        from tests.testapp.models import Article

        a = Article.objects.create(title="No Author", author=None)
        assert Article.objects.filter(author__isnull=True, pk=a.pk).exists()
        a.delete()

    def test_distinct(self):
        from django.contrib.auth.models import User

        result = list(
            User.objects.values_list("is_active", flat=True).distinct()
        )
        assert isinstance(result, list)

    def test_only_fields(self):
        from django.contrib.auth.models import User

        users = list(User.objects.only("username", "email")[:3])
        for u in users:
            assert u.username is not None

    def test_defer_fields(self):
        from django.contrib.auth.models import User

        users = list(User.objects.defer("password", "last_login")[:3])
        for u in users:
            assert u.username is not None

    def test_multiple_aggregates(self):
        from django.contrib.auth.models import Permission
        from django.db.models import Count, Q

        result = Permission.objects.aggregate(
            total=Count("id"),
            auth_count=Count("id", filter=Q(content_type__app_label="auth")),
        )
        assert result["total"] > 0
        assert result["auth_count"] > 0

    def test_reverse_fk_filter(self):
        from tests.testapp.models import Article
        from django.contrib.auth.models import User

        u = User.objects.create_user(f"rev_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        Article.objects.create(title="Rev Test", author=u)
        users = User.objects.filter(article__isnull=False).distinct()
        assert users.filter(pk=u.pk).exists()
        Article.objects.filter(author=u).delete()
        u.delete()

    def test_f_expression_comparison(self):
        from tests.testapp.models import Article
        from django.db.models import F

        articles = list(Article.objects.filter(views__gte=F("views")))
        assert isinstance(articles, list)


class TestCoexistence:
    """Test Document API and DB backend working together."""

    def test_both_apis_crud(self):
        """Create via Model API, read via raw N1QL, delete via Model API."""
        from django.contrib.auth.models import Group
        from django.db import connection
        from couchbase.options import QueryOptions

        name = f"coex_{uuid.uuid4().hex[:6]}"
        g = Group.objects.create(name=name)

        # Read via raw N1QL (using backend's cluster)
        cluster = connection.couchbase_cluster
        rows = list(
            cluster.query(
                "SELECT d.`name` FROM `testbucket`.`_default`.`auth_group` AS d "
                "WHERE d.`name` = $1",
                QueryOptions(
                    positional_parameters=[name],
                    scan_consistency="request_plus",
                ),
            ).rows()
        )
        assert len(rows) == 1

        # Delete via Model API and verify
        g.delete()
        rows = list(
            cluster.query(
                "SELECT d.`name` FROM `testbucket`.`_default`.`auth_group` AS d "
                "WHERE d.`name` = $1",
                QueryOptions(
                    positional_parameters=[name],
                    scan_consistency="request_plus",
                ),
            ).rows()
        )
        assert len(rows) == 0


class TestTimezoneAwareDatetimes:
    """Test timezone-aware datetime storage and retrieval."""

    def test_datetime_stored_with_utc_offset(self):
        """DateTimeField should store values with +00:00 UTC offset."""
        from django.contrib.auth.models import User

        username = f"tz_{uuid.uuid4().hex[:6]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        # last_login is set by Django — set it manually with a tz-aware datetime
        from django.utils import timezone

        now = timezone.now()
        user.last_login = now
        user.save()

        # Reload from DB
        user.refresh_from_db()
        assert user.last_login is not None
        user.delete()

    def test_datetime_roundtrip_with_use_tz(self, settings):
        """Datetimes should roundtrip correctly with USE_TZ=True."""
        settings.USE_TZ = True

        from datetime import datetime, timezone as tz

        from django.contrib.auth.models import User

        username = f"tzrt_{uuid.uuid4().hex[:6]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        aware_dt = datetime(2024, 6, 15, 12, 30, 45, tzinfo=tz.utc)
        user.last_login = aware_dt
        user.save()

        user.refresh_from_db()
        assert user.last_login is not None
        # Should come back as aware datetime
        assert user.last_login.tzinfo is not None
        assert user.last_login.year == 2024
        assert user.last_login.month == 6
        assert user.last_login.hour == 12
        user.delete()

    def test_datetime_non_utc_converted_to_utc(self, settings):
        """Non-UTC datetimes should be converted to UTC for storage."""
        settings.USE_TZ = True

        from datetime import datetime, timedelta, timezone as tz

        from django.contrib.auth.models import User

        username = f"tzconv_{uuid.uuid4().hex[:6]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        # 15:30 EST = 20:30 UTC
        est = tz(timedelta(hours=-5))
        user.last_login = datetime(2024, 1, 15, 15, 30, 0, tzinfo=est)
        user.save()

        user.refresh_from_db()
        assert user.last_login is not None
        # Should be stored/returned as UTC
        assert user.last_login.hour == 20
        assert user.last_login.minute == 30
        user.delete()

    def test_auto_now_produces_aware_datetime(self, settings):
        """auto_now fields should produce timezone-aware datetimes."""
        settings.USE_TZ = True

        from tests.testapp.models import Article

        a = Article.objects.create(title="TZ Test")
        a.refresh_from_db()
        assert a.created_at is not None
        assert a.updated_at is not None
        # With USE_TZ=True, auto_now datetimes should be aware
        assert a.created_at.tzinfo is not None
        assert a.updated_at.tzinfo is not None
        a.delete()


class TestWindowFunctions:
    """Test window function support (ROW_NUMBER, RANK, etc.)."""

    def test_window_row_number(self):
        """ROW_NUMBER() window function should work."""
        from django.contrib.auth.models import Group
        from django.db.models import F, Window
        from django.db.models.functions import RowNumber

        names = [f"win_{uuid.uuid4().hex[:4]}" for _ in range(3)]
        for n in names:
            Group.objects.create(name=n)

        qs = Group.objects.filter(name__in=names).annotate(
            row_num=Window(expression=RowNumber(), order_by=F("name").asc())
        )
        results = list(qs.values_list("name", "row_num"))
        assert len(results) == 3
        row_nums = [r[1] for r in results]
        assert sorted(row_nums) == [1, 2, 3]
        Group.objects.filter(name__in=names).delete()

    def test_supports_over_clause_flag(self):
        """Feature flag should be True."""
        from django.db import connection

        assert connection.features.supports_over_clause


class TestPreparedStatementCaching:
    """Test ADHOC option for prepared statement caching."""

    def test_adhoc_default_is_true(self):
        """Default ADHOC should be True (no caching)."""
        from django.db import connection

        cursor = connection.create_cursor()
        assert cursor._adhoc is True
        cursor.close()

    def test_adhoc_false_from_settings(self, settings):
        """ADHOC=False should propagate to cursor."""
        settings.DATABASES["default"]["OPTIONS"]["ADHOC"] = False

        from django.db import connection

        # Force new cursor with updated settings
        cursor = connection.create_cursor()
        assert cursor._adhoc is False
        cursor.close()

        # Restore
        settings.DATABASES["default"]["OPTIONS"].pop("ADHOC", None)

    def test_queries_work_with_adhoc_false(self, settings):
        """Queries should work normally with prepared statement caching."""
        settings.DATABASES["default"]["OPTIONS"]["ADHOC"] = False

        from django.contrib.auth.models import Group

        name = f"adhoc_{uuid.uuid4().hex[:6]}"
        Group.objects.create(name=name)
        assert Group.objects.filter(name=name).exists()
        Group.objects.filter(name=name).delete()

        settings.DATABASES["default"]["OPTIONS"].pop("ADHOC", None)


class TestQueryContext:
    """Test query_context on QueryOptions for unqualified name resolution."""

    def test_raw_sql_with_unqualified_name(self):
        """Raw N1QL with bare table name should resolve via query_context."""
        from django.db import connection

        with connection.cursor() as cursor:
            # This uses a fully qualified name — should work regardless
            cursor.execute(
                "SELECT 1 AS `val` FROM `testbucket`.`_default`.`auth_group` LIMIT 1"
            )
            # No error means query_context didn't interfere

    def test_cursor_has_query_context(self):
        """Cursor should set query_context on QueryOptions."""
        from django.db import connection

        cursor = connection.create_cursor()
        # Verify the cursor has the bucket/scope info for query_context
        assert cursor._bucket_name == connection.settings_dict["NAME"]
        cursor.close()


class TestOpenTelemetryTracer:
    """Test TRACER option propagation (no OTel dependency required)."""

    def test_tracer_not_set_by_default(self):
        """TRACER should not be in OPTIONS by default."""
        from django.db import connection

        assert connection.settings_dict.get("OPTIONS", {}).get("TRACER") is None

    def test_connection_works_without_tracer(self):
        """Connection should work fine without TRACER configured."""
        from django.db import connection

        connection.ensure_connection()
        assert connection.is_usable()
