"""Couchbase authentication backend for Django.

Usage in settings.py:
    AUTHENTICATION_BACKENDS = [
        "django_cb.contrib.auth.backend.CouchbaseAuthBackend",
    ]
"""

from __future__ import annotations

import logging

from django.contrib.auth.hashers import check_password, make_password

logger = logging.getLogger(__name__)

# Pre-computed unusable hash for constant-time dummy checks
_DUMMY_HASH = make_password(None)


class CouchbaseAuthBackend:
    """Authenticates users against Couchbase-backed User documents.

    Supports authentication by username or email.
    Does NOT implement permissions (has_perm always returns False).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Authenticate a user by username/email and password.

        Returns the User instance if credentials are valid, None otherwise.
        Runs the password hasher on every code path to prevent timing attacks.
        """
        from django_cb.contrib.auth.models import User

        if username is None or password is None:
            return None

        # Try username first, then email
        user = None
        try:
            user = User.get_by_username(username)
        except User.DoesNotExist:
            try:
                user = User.get_by_email(username)
            except User.DoesNotExist:
                pass

        # Always run the hasher — constant time regardless of user existence
        if user is not None:
            password_valid = check_password(password, user.password or _DUMMY_HASH)
            if password_valid and user.is_active:
                return user
        else:
            check_password(password, _DUMMY_HASH)

        return None

    def get_user(self, user_id):
        """Retrieve a user by their primary key (document ID)."""
        from django_cb.contrib.auth.models import User

        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    # ---- Permissions stubs (always False — no permission system) ----

    def has_perm(self, user_obj, perm, obj=None):
        return False

    def has_module_perms(self, user_obj, app_label):
        return False
