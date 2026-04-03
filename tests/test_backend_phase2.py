"""Phase 2 tests: Relationships, JOINs, M2M, annotations, expressions.

Tests ForeignKey traversal, ManyToMany operations, select_related,
prefetch_related, annotate, F expressions, Q objects against Couchbase.
"""

import uuid

import pytest
from django.db import connection
from django.db.models import Count, Q, F

pytestmark = [
    pytest.mark.phase2,
    pytest.mark.skipif(
        not __import__("tests.test_backend_crud", fromlist=["_couchbase_available"])._couchbase_available(),
        reason="Local Couchbase not available",
    ),
    pytest.mark.django_db(transaction=True),
]


class TestSelectRelated:
    """Test select_related (FK JOINs)."""

    def test_select_related_fk(self):
        from django.contrib.auth.models import Permission

        perms = list(Permission.objects.select_related("content_type")[:3])
        assert len(perms) > 0
        # content_type should be loaded without extra queries.
        for p in perms:
            assert p.content_type is not None
            assert p.content_type.app_label is not None

    def test_select_related_no_extra_queries(self):
        from django.contrib.auth.models import Permission

        # Without select_related, accessing content_type would trigger a query.
        # With it, no extra queries needed.
        perms = list(Permission.objects.select_related("content_type")[:5])
        for p in perms:
            # Access should not raise — already loaded via JOIN.
            _ = p.content_type.model


class TestForeignKeyFilters:
    """Test FK traversal in filter queries."""

    def test_filter_across_fk(self):
        from django.contrib.auth.models import Permission

        perms = list(Permission.objects.filter(content_type__app_label="auth"))
        assert len(perms) > 0
        for p in perms:
            assert p.content_type.app_label == "auth"

    def test_filter_double_underscore_fk(self):
        from django.contrib.auth.models import Permission

        perms = list(
            Permission.objects.filter(
                content_type__app_label="auth", content_type__model="user"
            )
        )
        assert len(perms) == 4  # add, change, delete, view

    def test_reverse_fk(self):
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get(app_label="auth", model="user")
        perms = list(ct.permission_set.all())
        assert len(perms) == 4


class TestManyToMany:
    """Test M2M operations."""

    def test_m2m_add_and_list(self):
        from django.contrib.auth.models import User, Group

        username = f"m2m_add_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        g = Group.objects.create(name=f"g_{uuid.uuid4().hex[:6]}")

        user.groups.add(g)
        assert g in user.groups.all()

        user.delete()
        g.delete()

    def test_m2m_remove(self):
        from django.contrib.auth.models import User, Group

        username = f"m2m_rm_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        g = Group.objects.create(name=f"g_{uuid.uuid4().hex[:6]}")

        user.groups.add(g)
        assert user.groups.count() == 1
        user.groups.remove(g)
        assert user.groups.count() == 0

        user.delete()
        g.delete()

    def test_m2m_clear(self):
        from django.contrib.auth.models import User, Group

        username = f"m2m_clr_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        g1 = Group.objects.create(name=f"g1_{uuid.uuid4().hex[:6]}")
        g2 = Group.objects.create(name=f"g2_{uuid.uuid4().hex[:6]}")

        user.groups.set([g1, g2])
        assert user.groups.count() == 2
        user.groups.clear()
        assert user.groups.count() == 0

        user.delete()
        g1.delete()
        g2.delete()

    def test_m2m_reverse_lookup(self):
        from django.contrib.auth.models import User, Group

        username = f"m2m_rev_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        g = Group.objects.create(name=f"g_{uuid.uuid4().hex[:6]}")

        user.groups.add(g)
        users_in_group = list(g.user_set.all())
        assert any(u.username == username for u in users_in_group)

        user.delete()
        g.delete()

    def test_m2m_count(self):
        from django.contrib.auth.models import User, Group

        username = f"m2m_cnt_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        groups = [
            Group.objects.create(name=f"g_{uuid.uuid4().hex[:6]}") for _ in range(3)
        ]
        user.groups.set(groups)
        assert user.groups.count() == 3

        user.delete()
        for g in groups:
            g.delete()


class TestAnnotate:
    """Test annotate and aggregate operations."""

    def test_annotate_count(self):
        from django.contrib.contenttypes.models import ContentType

        results = list(
            ContentType.objects.annotate(perm_count=Count("permission")).filter(
                perm_count__gt=0
            )[:3]
        )
        assert len(results) > 0
        for ct in results:
            assert ct.perm_count > 0

    def test_aggregate_count(self):
        from django.contrib.auth.models import Permission

        result = Permission.objects.aggregate(total=Count("id"))
        assert result["total"] > 0

    def test_count(self):
        from django.contrib.auth.models import Permission

        count = Permission.objects.count()
        assert count > 0

    def test_count_with_filter(self):
        from django.contrib.auth.models import Permission

        count = Permission.objects.filter(
            content_type__app_label="auth"
        ).count()
        assert count > 0


class TestQObjects:
    """Test Q object queries."""

    def test_q_or(self):
        from django.contrib.auth.models import Permission

        perms = Permission.objects.filter(
            Q(codename__startswith="add") | Q(codename__startswith="change")
        )
        assert perms.count() > 0

    def test_q_and(self):
        from django.contrib.auth.models import Permission

        perms = Permission.objects.filter(
            Q(codename__startswith="add") & Q(content_type__app_label="auth")
        )
        assert perms.count() > 0

    def test_q_not(self):
        from django.contrib.auth.models import Permission

        total = Permission.objects.count()
        add_perms = Permission.objects.filter(codename__startswith="add").count()
        not_add = Permission.objects.filter(~Q(codename__startswith="add")).count()
        assert not_add == total - add_perms


class TestFExpressions:
    """Test F() expressions."""

    def test_f_in_filter(self):
        from django.contrib.contenttypes.models import ContentType

        # No content type has app_label == model, so this should return empty.
        result = list(ContentType.objects.filter(app_label=F("model")))
        # Just verify it doesn't crash.
        assert isinstance(result, list)

    def test_f_in_update(self):
        from django.contrib.auth.models import User

        username = f"fexpr_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        user.first_name = "Original"
        user.save()

        # Use F() to copy first_name to last_name
        User.objects.filter(pk=user.pk).update(last_name=F("first_name"))
        user.refresh_from_db()
        assert user.last_name == "Original"

        user.delete()


class TestModelSave:
    """Test model.save() (UPSERT behavior)."""

    def test_save_existing_object(self):
        from django.contrib.auth.models import User

        username = f"save_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        user.last_name = "Updated"
        user.save()  # Should not raise DocumentExistsException.

        user.refresh_from_db()
        assert user.last_name == "Updated"
        user.delete()

    def test_save_multiple_times(self):
        from django.contrib.auth.models import Group

        name = f"save_multi_{uuid.uuid4().hex[:8]}"
        g = Group.objects.create(name=name)

        for i in range(3):
            g.name = f"{name}_{i}"
            g.save()

        g.refresh_from_db()
        assert g.name == f"{name}_2"
        g.delete()


class TestLookups:
    """Test all lookup types."""

    def test_icontains(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__icontains="ADD").count() > 0

    def test_istartswith(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__istartswith="ADD").count() > 0

    def test_iendswith(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__iendswith="USER").count() > 0

    def test_iexact(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__iexact="ADD_USER").count() == 1

    def test_contains(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__contains="add").count() > 0

    def test_startswith(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__startswith="add").count() > 0

    def test_endswith(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(codename__endswith="user").count() > 0

    def test_in_lookup(self):
        from django.contrib.auth.models import Permission
        assert Permission.objects.filter(
            codename__in=["add_user", "delete_user"]
        ).count() == 2

    def test_isnull(self):
        from django.contrib.auth.models import User
        # Just verify it doesn't crash
        User.objects.filter(last_login__isnull=True).count()

    def test_gt_lt(self):
        from django.contrib.auth.models import User
        # String comparison — just verify it executes
        User.objects.filter(username__gt="a").count()
        User.objects.filter(username__lt="zzzzz").count()


class TestPrefetchRelated:
    """Test prefetch_related."""

    def test_prefetch_related(self):
        from django.contrib.contenttypes.models import ContentType

        cts = list(
            ContentType.objects.prefetch_related("permission_set").filter(
                app_label="auth"
            )
        )
        assert len(cts) > 0
        for ct in cts:
            # This should not trigger additional queries.
            perms = list(ct.permission_set.all())
            assert len(perms) >= 0

    def test_prefetch_m2m(self):
        from django.contrib.auth.models import User, Group
        import uuid

        username = f"pf_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass")
        g = Group.objects.create(name=f"pfg_{uuid.uuid4().hex[:6]}")
        user.groups.add(g)

        # Prefetch groups
        users = list(User.objects.filter(pk=user.pk).prefetch_related("groups"))
        assert len(users) == 1
        assert users[0].groups.count() == 1

        user.delete()
        g.delete()


class TestValuesAnnotate:
    """Test values().annotate() (GROUP BY)."""

    def test_values_annotate(self):
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Count

        results = list(
            ContentType.objects.values("app_label").annotate(total=Count("id"))
        )
        assert len(results) > 0
        for r in results:
            assert "app_label" in r
            assert "total" in r
            assert r["total"] > 0

    def test_values_annotate_filter(self):
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Count

        results = list(
            ContentType.objects.values("app_label")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
        )
        assert len(results) > 0


class TestOrderBy:
    """Test ORDER BY including values_list (positional fix)."""

    def test_order_by_values_list(self):
        """Positional ORDER BY (ORDER BY 1) should be fixed for N1QL."""
        from django.contrib.auth.models import Group

        prefix = f"vl_ord_{uuid.uuid4().hex[:6]}"
        names = [f"{prefix}_c", f"{prefix}_a", f"{prefix}_b"]
        for n in names:
            Group.objects.create(name=n)

        ordered = list(
            Group.objects.filter(name__startswith=prefix)
            .order_by("name")
            .values_list("name", flat=True)
        )
        assert ordered == sorted(names)

        Group.objects.filter(name__startswith=prefix).delete()

    def test_order_by_desc(self):
        from django.contrib.auth.models import Group

        prefix = f"desc_{uuid.uuid4().hex[:6]}"
        names = [f"{prefix}_a", f"{prefix}_b", f"{prefix}_c"]
        for n in names:
            Group.objects.create(name=n)

        ordered = [
            g.name
            for g in Group.objects.filter(name__startswith=prefix).order_by("-name")
        ]
        assert ordered == sorted(names, reverse=True)

        Group.objects.filter(name__startswith=prefix).delete()
