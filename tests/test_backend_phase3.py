"""Phase 3 tests: Django Ecosystem — Admin, Auth, Forms, Sessions, ContentTypes.

Tests full Django ecosystem integration against Couchbase backend.
"""

import uuid

import pytest

pytestmark = [
    pytest.mark.phase3,
    pytest.mark.skipif(
        not __import__("tests.test_backend_crud", fromlist=["_couchbase_available"])._couchbase_available(),
        reason="Local Couchbase not available",
    ),
    pytest.mark.django_db(transaction=True),
]


class TestAuthPermissions:
    """Test Django's full permission system."""

    def test_has_perm_user_permission(self):
        from django.contrib.auth.models import User, Permission

        u = User.objects.create_user(f"p_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        perm = Permission.objects.get(codename="add_user")
        u.user_permissions.add(perm)
        # Re-fetch to clear cached permissions.
        u = User.objects.get(pk=u.pk)
        assert u.has_perm("auth.add_user")
        u.delete()

    def test_has_perm_group_permission(self):
        from django.contrib.auth.models import User, Group, Permission

        u = User.objects.create_user(f"gp_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        g = Group.objects.create(name=f"gp_{uuid.uuid4().hex[:6]}")
        perm = Permission.objects.get(codename="change_user")
        g.permissions.add(perm)
        u.groups.add(g)
        u = User.objects.get(pk=u.pk)
        assert u.has_perm("auth.change_user")
        u.delete()
        g.delete()

    def test_superuser_has_all_perms(self):
        from django.contrib.auth.models import User

        u = User.objects.create_superuser(f"su_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        assert u.has_perm("anything.anything")
        assert u.has_module_perms("anything")
        u.delete()

    def test_get_all_permissions(self):
        from django.contrib.auth.models import User, Group, Permission

        u = User.objects.create_user(f"ap_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        g = Group.objects.create(name=f"ap_{uuid.uuid4().hex[:6]}")
        perm1 = Permission.objects.get(codename="add_user")
        perm2 = Permission.objects.get(codename="change_user")
        u.user_permissions.add(perm1)
        g.permissions.add(perm2)
        u.groups.add(g)
        u = User.objects.get(pk=u.pk)
        all_perms = u.get_all_permissions()
        assert "auth.add_user" in all_perms
        assert "auth.change_user" in all_perms
        u.delete()
        g.delete()

    def test_inactive_user_no_perms(self):
        from django.contrib.auth.models import User, Permission

        u = User.objects.create_user(f"in_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        perm = Permission.objects.get(codename="add_user")
        u.user_permissions.add(perm)
        u.is_active = False
        u.save()
        u = User.objects.get(pk=u.pk)
        assert not u.has_perm("auth.add_user")
        u.delete()


class TestDjangoAdmin:
    """Test Django admin interface."""

    def _get_admin_client(self):
        from django.contrib.auth.models import User
        from django.test import Client

        username = f"admin_{uuid.uuid4().hex[:6]}"
        user = User.objects.create_superuser(username, "admin@test.com", "testpass")
        client = Client()
        client.login(username=username, password="testpass")
        return client, user

    def test_admin_index(self):
        client, user = self._get_admin_client()
        response = client.get("/admin/")
        assert response.status_code == 200
        user.delete()

    def test_admin_user_changelist(self):
        client, user = self._get_admin_client()
        response = client.get("/admin/auth/user/")
        assert response.status_code == 200
        user.delete()

    def test_admin_group_changelist(self):
        client, user = self._get_admin_client()
        response = client.get("/admin/auth/group/")
        assert response.status_code == 200
        user.delete()

    def test_admin_group_add(self):
        from django.contrib.auth.models import Group

        client, user = self._get_admin_client()
        response = client.get("/admin/auth/group/add/")
        assert response.status_code == 200

        # POST to create
        name = f"admin_add_{uuid.uuid4().hex[:6]}"
        response = client.post("/admin/auth/group/add/", {"name": name}, follow=True)
        assert response.status_code == 200
        assert Group.objects.filter(name=name).exists()
        Group.objects.filter(name=name).delete()
        user.delete()

    def test_admin_group_change(self):
        from django.contrib.auth.models import Group

        client, user = self._get_admin_client()
        g = Group.objects.create(name=f"admin_chg_{uuid.uuid4().hex[:6]}")

        response = client.get(f"/admin/auth/group/{g.pk}/change/")
        assert response.status_code == 200
        g.delete()
        user.delete()

    def test_admin_group_delete(self):
        from django.contrib.auth.models import Group

        client, user = self._get_admin_client()
        g = Group.objects.create(name=f"admin_del_{uuid.uuid4().hex[:6]}")
        pk = g.pk

        response = client.post(
            f"/admin/auth/group/{pk}/delete/", {"post": "yes"}, follow=True
        )
        assert response.status_code == 200
        assert not Group.objects.filter(pk=pk).exists()
        user.delete()

    def test_admin_search(self):
        from django.contrib.auth.models import User

        client, user = self._get_admin_client()
        User.objects.create_user(
            f"searchable_{uuid.uuid4().hex[:6]}", "s@test.com", "pass"
        )

        response = client.get("/admin/auth/user/?q=searchable")
        assert response.status_code == 200
        User.objects.filter(username__startswith="searchable").delete()
        user.delete()


class TestModelForms:
    """Test Django ModelForm integration."""

    def test_model_form_create(self):
        from django import forms
        from django.contrib.auth.models import Group

        class GroupForm(forms.ModelForm):
            class Meta:
                model = Group
                fields = ["name"]

        form = GroupForm(data={"name": f"mf_{uuid.uuid4().hex[:6]}"})
        assert form.is_valid(), form.errors
        obj = form.save()
        assert obj.pk is not None
        obj.delete()

    def test_model_form_update(self):
        from django import forms
        from django.contrib.auth.models import Group

        class GroupForm(forms.ModelForm):
            class Meta:
                model = Group
                fields = ["name"]

        g = Group.objects.create(name=f"mfu_{uuid.uuid4().hex[:6]}")
        form = GroupForm(data={"name": "updated"}, instance=g)
        assert form.is_valid()
        obj = form.save()
        assert obj.name == "updated"
        obj.delete()

    def test_user_creation_form(self):
        from django.contrib.auth.forms import UserCreationForm

        form = UserCreationForm(
            data={
                "username": f"ucf_{uuid.uuid4().hex[:6]}",
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        assert form.is_valid(), form.errors
        user = form.save()
        assert user.pk is not None
        user.delete()

    def test_authentication_form(self):
        from django.contrib.auth.forms import AuthenticationForm
        from django.contrib.auth.models import User
        from django.test import RequestFactory

        username = f"af_{uuid.uuid4().hex[:6]}"
        User.objects.create_user(username, "x@x.com", "testpass123")
        rf = RequestFactory()
        request = rf.get("/")
        form = AuthenticationForm(
            request, data={"username": username, "password": "testpass123"}
        )
        assert form.is_valid(), form.errors
        User.objects.filter(username=username).first().delete()


class TestSessions:
    """Test Django DB session backend."""

    def test_session_create_read(self):
        from django.contrib.sessions.backends.db import SessionStore

        s = SessionStore()
        s["key"] = "value"
        s.create()
        assert s.session_key is not None

        s2 = SessionStore(session_key=s.session_key)
        assert s2["key"] == "value"
        s.delete()

    def test_session_modify(self):
        from django.contrib.sessions.backends.db import SessionStore

        s = SessionStore()
        s["key"] = "original"
        s.create()

        s["key"] = "modified"
        s.save()

        s2 = SessionStore(session_key=s.session_key)
        assert s2["key"] == "modified"
        s.delete()

    def test_session_delete(self):
        from django.contrib.sessions.backends.db import SessionStore

        s = SessionStore()
        s["key"] = "value"
        s.create()
        key = s.session_key

        s.delete()
        s2 = SessionStore(session_key=key)
        assert s2.get("key") is None


class TestContentTypes:
    """Test ContentType framework integration."""

    def test_get_for_model(self):
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(User)
        assert ct.app_label == "auth"
        assert ct.model == "user"

    def test_get_object_for_this_type(self):
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(User)
        u = User.objects.create_user(f"ct_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        obj = ct.get_object_for_this_type(pk=u.pk)
        assert obj.pk == u.pk
        u.delete()

    def test_model_class(self):
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(User)
        assert ct.model_class() is User


class TestAdminLogEntry:
    """Test admin LogEntry."""

    def test_log_action(self):
        from django.contrib.admin.models import LogEntry, ADDITION
        from django.contrib.auth.models import User
        from django.contrib.contenttypes.models import ContentType

        u = User.objects.create_superuser(f"le_{uuid.uuid4().hex[:6]}", "x@x.com", "p")
        ct = ContentType.objects.get_for_model(User)

        LogEntry.objects.create(
            user=u,
            content_type=ct,
            object_id=str(u.pk),
            object_repr=str(u),
            action_flag=ADDITION,
        )
        assert LogEntry.objects.filter(user=u).count() == 1
        u.delete()
