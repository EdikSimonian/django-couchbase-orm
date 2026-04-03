"""Integration tests for the Couchbase Django database backend.

Tests core django.db.models.Model operations against a real Couchbase instance.

Requires: docker run -d --name couchbase-test -p 8091-8097:8091-8097 -p 11210-11211:11210-11211 couchbase/server:latest
"""

import uuid

import pytest
from django.db import connection, models
from django.test import override_settings

from django_couchbase_orm.db.backends.couchbase.cursor import (
    CouchbaseCursor,
    _parse_select_columns,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _couchbase_available():
    try:
        import socket
        s = socket.socket()
        s.settimeout(2)
        s.connect(("localhost", 8091))
        s.close()
        return True
    except Exception:
        return False


BACKEND_SETTINGS = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "testbucket",
        "USER": "Administrator",
        "PASSWORD": "password",
        "HOST": "couchbase://localhost",
        "OPTIONS": {"SCOPE": "_default"},
    }
}

pytestmark = [
    pytest.mark.backend,
    pytest.mark.skipif(not _couchbase_available(), reason="Local Couchbase not available"),
    pytest.mark.django_db(transaction=True),
]


# ===================================================================
# Unit tests — no Couchbase required
# ===================================================================

class TestParseSelectColumns:
    """Test the SELECT column parser used by CouchbaseCursor."""

    def test_simple_columns(self):
        sql = "SELECT `id`, `name`, `age` FROM `bucket`.`scope`.`table`"
        assert _parse_select_columns(sql) == ["id", "name", "age"]

    def test_aliased_columns(self):
        sql = "SELECT `t`.`id` AS `pk`, `t`.`name` FROM `bucket`.`scope`.`t`"
        assert _parse_select_columns(sql) == ["pk", "name"]

    def test_select_star_returns_none(self):
        sql = "SELECT * FROM `bucket`.`scope`.`table`"
        assert _parse_select_columns(sql) is None

    def test_select_d_star_returns_none(self):
        sql = "SELECT d.* FROM `bucket`.`scope`.`table` AS d"
        assert _parse_select_columns(sql) is None

    def test_function_in_select(self):
        sql = "SELECT COUNT(*) AS `__count` FROM `bucket`.`scope`.`t`"
        result = _parse_select_columns(sql)
        assert result == ["__count"]

    def test_distinct(self):
        sql = "SELECT DISTINCT `name`, `age` FROM `bucket`.`scope`.`t`"
        assert _parse_select_columns(sql) == ["name", "age"]

    def test_dotted_columns(self):
        sql = "SELECT d.name, d.age FROM table AS d"
        assert _parse_select_columns(sql) == ["name", "age"]

    def test_non_select_returns_none(self):
        sql = "DELETE FROM `bucket`.`scope`.`t` WHERE id = $1"
        assert _parse_select_columns(sql) is None


class TestInClauseCollapse:
    """Test the IN (%s, %s, ...) -> IN %s array conversion."""

    def test_single_in(self):
        sql = "SELECT * FROM t WHERE x IN (%s, %s, %s)"
        params = ["a", "b", "c"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == "SELECT * FROM t WHERE x IN %s"
        assert new_params == [["a", "b", "c"]]

    def test_in_with_other_params(self):
        sql = "SELECT * FROM t WHERE y = %s AND x IN (%s, %s) AND z = %s"
        params = ["val1", "a", "b", "val2"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == "SELECT * FROM t WHERE y = %s AND x IN %s AND z = %s"
        assert new_params == ["val1", ["a", "b"], "val2"]

    def test_no_in_clause(self):
        sql = "SELECT * FROM t WHERE x = %s"
        params = ["a"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == sql
        assert new_params == params

    def test_single_value_in(self):
        sql = "SELECT * FROM t WHERE x IN (%s)"
        params = ["a"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == "SELECT * FROM t WHERE x IN %s"
        assert new_params == [["a"]]

    def test_multiple_in_clauses(self):
        sql = "SELECT * FROM t WHERE x IN (%s, %s) AND y IN (%s, %s, %s)"
        params = ["a", "b", 1, 2, 3]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == "SELECT * FROM t WHERE x IN %s AND y IN %s"
        assert new_params == [["a", "b"], [1, 2, 3]]


class TestParamConversion:
    """Test %s -> $N parameter conversion."""

    def test_simple_params(self):
        cursor = CouchbaseCursor.__new__(CouchbaseCursor)
        sql, params = cursor._convert_params(
            "SELECT * FROM t WHERE x = %s AND y = %s", ("a", "b")
        )
        assert sql == "SELECT * FROM t WHERE x = $1 AND y = $2"
        assert params == ["a", "b"]

    def test_no_params(self):
        cursor = CouchbaseCursor.__new__(CouchbaseCursor)
        sql, params = cursor._convert_params("SELECT * FROM t", None)
        assert sql == "SELECT * FROM t"
        assert params == []

    def test_escaped_percent(self):
        cursor = CouchbaseCursor.__new__(CouchbaseCursor)
        sql, params = cursor._convert_params(
            "SELECT * FROM t WHERE x LIKE %%s%% AND y = %s", ("val",)
        )
        # %%s%% should remain as %s% (unescaped), only the lone %s converts
        assert "$1" in sql
        assert params == ["val"]


# ===================================================================
# Integration tests — require Couchbase
# ===================================================================


class TestBackendConnection:
    """Test basic backend connection."""

    def test_vendor(self):
        assert connection.vendor == "couchbase"

    def test_connection_usable(self):
        connection.ensure_connection()
        assert connection.connection is not None

    def test_cursor_creation(self):
        with connection.cursor() as cursor:
            assert cursor is not None


class TestCursorExecute:
    """Test raw N1QL execution via the cursor."""

    def test_simple_select(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 AS `val` FROM `testbucket`.`_default`.`django_content_type` LIMIT 1"
            )
            row = cursor.fetchone()
            assert row is not None

    def test_select_with_params(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT `app_label` FROM `testbucket`.`_default`.`django_content_type` "
                "WHERE `app_label` = %s LIMIT 1",
                ("auth",),
            )
            row = cursor.fetchone()
            if row:
                assert row[0] == "auth"

    def test_fetchall(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT `app_label` FROM `testbucket`.`_default`.`django_content_type`"
            )
            rows = cursor.fetchall()
            assert isinstance(rows, list)

    def test_empty_result(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM `testbucket`.`_default`.`django_content_type` "
                "WHERE `app_label` = %s",
                ("nonexistent_app_label_xyz",),
            )
            assert cursor.fetchone() is None
            assert cursor.fetchall() == []


class TestModelCRUD:
    """Test Django Model CRUD via the backend."""

    def test_create_and_get_user(self):
        from django.contrib.auth.models import User

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")
        assert user.pk is not None

        retrieved = User.objects.get(pk=user.pk)
        assert retrieved.username == username
        assert retrieved.email == f"{username}@test.com"

        # Cleanup
        user.delete()

    def test_create_sets_integer_pk(self):
        from django.contrib.auth.models import Group

        name = f"group_{uuid.uuid4().hex[:8]}"
        group = Group.objects.create(name=name)
        assert group.pk is not None
        assert isinstance(group.pk, int)
        assert group.pk >= 1
        group.delete()

    def test_filter(self):
        from django.contrib.auth.models import User

        username = f"filtertest_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")

        qs = User.objects.filter(username=username)
        assert qs.count() == 1
        assert qs.first().username == username

        user.delete()

    def test_filter_multiple_conditions(self):
        from django.contrib.auth.models import User

        username = f"multi_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        qs = User.objects.filter(username=username, is_active=True)
        assert qs.count() == 1

        qs2 = User.objects.filter(username=username, is_active=False)
        assert qs2.count() == 0

        User.objects.filter(username=username).first().delete()

    def test_exclude(self):
        from django.contrib.auth.models import User

        username = f"excl_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        qs = User.objects.exclude(username=username)
        usernames = list(qs.values_list("username", flat=True))
        assert username not in usernames

        User.objects.filter(username=username).first().delete()

    def test_update(self):
        from django.contrib.auth.models import User

        username = f"upd_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")

        User.objects.filter(pk=user.pk).update(first_name="Updated")
        user.refresh_from_db()
        assert user.first_name == "Updated"

        user.delete()

    def test_save_update(self):
        from django.contrib.auth.models import User

        username = f"save_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")
        user.last_name = "SaveTest"
        user.save()

        retrieved = User.objects.get(pk=user.pk)
        assert retrieved.last_name == "SaveTest"

        user.delete()

    def test_delete(self):
        from django.contrib.auth.models import Group

        name = f"del_{uuid.uuid4().hex[:8]}"
        group = Group.objects.create(name=name)
        pk = group.pk
        group.delete()
        assert not Group.objects.filter(pk=pk).exists()

    def test_bulk_delete(self):
        from django.contrib.auth.models import Group

        names = [f"bulk_{uuid.uuid4().hex[:8]}" for _ in range(3)]
        for n in names:
            Group.objects.create(name=n)

        assert Group.objects.filter(name__in=names).count() == 3
        Group.objects.filter(name__in=names).delete()
        assert Group.objects.filter(name__in=names).count() == 0

    def test_exists(self):
        from django.contrib.auth.models import Group

        name = f"exists_{uuid.uuid4().hex[:8]}"
        assert not Group.objects.filter(name=name).exists()
        g = Group.objects.create(name=name)
        assert Group.objects.filter(name=name).exists()
        g.delete()

    def test_count(self):
        from django.contrib.auth.models import Group

        name = f"cnt_{uuid.uuid4().hex[:8]}"
        initial = Group.objects.count()
        g = Group.objects.create(name=name)
        assert Group.objects.count() == initial + 1
        g.delete()

    def test_first_and_last(self):
        from django.contrib.auth.models import User

        first = User.objects.first()
        # Just verify it doesn't crash — may be None if no users.
        assert first is None or hasattr(first, "username")

    def test_values(self):
        from django.contrib.auth.models import User

        username = f"vals_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        result = User.objects.filter(username=username).values("username", "email")
        rows = list(result)
        assert len(rows) == 1
        assert rows[0]["username"] == username
        assert rows[0]["email"] == f"{username}@test.com"

        User.objects.filter(username=username).first().delete()

    def test_values_list(self):
        from django.contrib.auth.models import User

        username = f"vlist_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        result = list(
            User.objects.filter(username=username).values_list("username", flat=True)
        )
        assert result == [username]

        User.objects.filter(username=username).first().delete()

    def test_order_by(self):
        from django.contrib.auth.models import Group

        prefix = f"ord_{uuid.uuid4().hex[:6]}"
        names = [f"{prefix}_c", f"{prefix}_a", f"{prefix}_b"]
        for n in names:
            Group.objects.create(name=n)

        # Use full object query (not values_list) to avoid N1QL's lack
        # of positional ORDER BY (ORDER BY 1).
        ordered = [
            g.name
            for g in Group.objects.filter(name__startswith=prefix).order_by("name")
        ]
        assert ordered == sorted(names)

        Group.objects.filter(name__startswith=prefix).delete()

    def test_slicing(self):
        from django.contrib.auth.models import Group

        names = [f"slc_{uuid.uuid4().hex[:4]}_{i}" for i in range(5)]
        for n in names:
            Group.objects.create(name=n)

        sliced = Group.objects.filter(name__in=names).order_by("name")[:2]
        assert len(sliced) == 2

        Group.objects.filter(name__in=names).delete()

    def test_get_nonexistent_raises(self):
        from django.contrib.auth.models import User

        with pytest.raises(User.DoesNotExist):
            User.objects.get(username=f"nonexistent_{uuid.uuid4().hex}")


class TestContentTypes:
    """Test Django ContentType framework."""

    def test_get_for_model(self):
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(User)
        assert ct.app_label == "auth"
        assert ct.model == "user"
        assert ct.pk is not None

    def test_get_for_model_idempotent(self):
        from django.contrib.auth.models import Group
        from django.contrib.contenttypes.models import ContentType

        ct1 = ContentType.objects.get_for_model(Group)
        ct2 = ContentType.objects.get_for_model(Group)
        assert ct1.pk == ct2.pk


class TestAuth:
    """Test Django auth with the backend."""

    def test_password_hashing(self):
        from django.contrib.auth.models import User

        username = f"pw_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "secret123")
        assert user.check_password("secret123")
        assert not user.check_password("wrong")
        user.delete()

    def test_superuser_flags(self):
        from django.contrib.auth.models import User

        username = f"su_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_superuser(username, f"{username}@test.com", "secret")
        assert user.is_superuser
        assert user.is_staff
        user.delete()

    def test_authenticate(self):
        from django.contrib.auth import authenticate

        username = f"auth_{uuid.uuid4().hex[:8]}"
        from django.contrib.auth.models import User
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        authed = authenticate(username=username, password="pass123")
        assert authed is not None
        assert authed.username == username

        bad = authenticate(username=username, password="wrong")
        assert bad is None

        User.objects.filter(username=username).first().delete()


class TestSchemaEditor:
    """Test schema operations."""

    def test_collection_exists_after_migrate(self):
        """Verify that migrate created the expected collections."""
        tables = [t.name for t in connection.introspection.get_table_list(None)]
        assert "django_content_type" in tables
        assert "auth_user" in tables
        assert "auth_group" in tables
        assert "auth_permission" in tables
        assert "django_migrations" in tables


class TestDatabaseOperations:
    """Test DatabaseOperations methods."""

    def test_quote_name(self):
        assert connection.ops.quote_name("table") == "`table`"

    def test_quote_name_already_quoted(self):
        assert connection.ops.quote_name("`table`") == "`table`"

    def test_adapt_datefield(self):
        import datetime
        result = connection.ops.adapt_datefield_value(datetime.date(2024, 1, 15))
        assert result == "2024-01-15"

    def test_adapt_datetimefield(self):
        import datetime
        result = connection.ops.adapt_datetimefield_value(
            datetime.datetime(2024, 1, 15, 10, 30, 0)
        )
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_adapt_none(self):
        assert connection.ops.adapt_datefield_value(None) is None
        assert connection.ops.adapt_datetimefield_value(None) is None

    def test_sql_flush(self):
        sqls = connection.ops.sql_flush(None, ["test_table"])
        assert len(sqls) == 1
        assert "DELETE FROM" in sqls[0]
        assert "test_table" in sqls[0]


class TestDatabaseFeatures:
    """Test feature flags are set correctly."""

    def test_no_transactions(self):
        assert not connection.features.supports_transactions

    def test_no_savepoints(self):
        assert not connection.features.uses_savepoints

    def test_json_support(self):
        assert connection.features.supports_json_field
        assert connection.features.has_native_json_field

    def test_no_fk_constraints(self):
        assert not connection.features.supports_foreign_keys

    def test_bulk_insert(self):
        assert connection.features.has_bulk_insert
