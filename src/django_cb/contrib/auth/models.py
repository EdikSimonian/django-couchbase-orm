"""Couchbase-backed User model for Django authentication.

Provides a User document that supports password hashing and authentication
without relying on Django's ORM or permissions framework.
"""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password

from django_cb.document import Document
from django_cb.fields.datetime import DateTimeField
from django_cb.fields.simple import BooleanField, StringField


class User(Document):
    """A Couchbase-backed user model for authentication.

    Compatible with Django's authentication system via the CouchbaseAuthBackend.
    Does NOT implement permissions or groups.
    """

    username = StringField(required=True)
    email = StringField()
    password = StringField()  # Stores hashed password
    first_name = StringField()
    last_name = StringField()
    is_active = BooleanField(default=True)
    is_staff = BooleanField(default=False)
    is_superuser = BooleanField(default=False)
    last_login = DateTimeField()
    date_joined = DateTimeField(auto_now_add=True)

    class Meta:
        collection_name = "_default"
        doc_type_field = "_type"

    # ---- Django auth compatibility interface ----

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_authenticated(self) -> bool:
        return True

    def get_username(self) -> str:
        return self.username

    def get_full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def get_short_name(self) -> str:
        return self.first_name or self.username

    def set_password(self, raw_password: str) -> None:
        """Hash and set the user's password."""
        self._data["password"] = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Check a raw password against the stored hash."""
        return check_password(raw_password, self.password or "")

    def set_unusable_password(self) -> None:
        self._data["password"] = make_password(None)

    def has_usable_password(self) -> bool:
        return self.password is not None and not self.password.startswith("!")

    def __str__(self) -> str:
        return self.username or self.pk

    @classmethod
    def create_user(
        cls,
        username: str,
        email: str | None = None,
        password: str | None = None,
        _id: str | None = None,
        **extra_fields,
    ) -> User:
        """Create and save a regular user."""
        user = cls(_id=_id or f"user::{username}", username=username, email=email or "", **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    @classmethod
    def create_superuser(
        cls, username: str, email: str | None = None, password: str | None = None, **extra_fields
    ) -> User:
        """Create and save a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return cls.create_user(username, email, password, **extra_fields)

    @classmethod
    def get_by_username(cls, username: str) -> User:
        """Fetch a user by username using N1QL query."""
        return cls.objects.get(username=username)

    @classmethod
    def get_by_email(cls, email: str) -> User:
        """Fetch a user by email using N1QL query."""
        return cls.objects.get(email=email)
