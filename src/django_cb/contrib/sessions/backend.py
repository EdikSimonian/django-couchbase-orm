"""Couchbase session backend for Django.

Stores sessions as Couchbase KV documents with TTL-based expiry.
Session data is JSON-serialized and stored with a configurable key prefix.

Usage in settings.py:
    SESSION_ENGINE = "django_cb.contrib.sessions.backend"
"""

import logging
from datetime import timedelta

from django.contrib.sessions.backends.base import CreateError, SessionBase

logger = logging.getLogger(__name__)

SESSION_KEY_PREFIX = "session:"


class SessionStore(SessionBase):
    """Django session backend using Couchbase KV operations.

    Sessions are stored as JSON documents with Couchbase TTL for automatic expiry.
    """

    def _get_collection(self):
        from django.conf import settings

        from django_cb.connection import get_collection

        session_settings = getattr(settings, "COUCHBASE_SESSION", {})
        alias = session_settings.get("ALIAS", "default")
        scope = session_settings.get("SCOPE", None)
        collection = session_settings.get("COLLECTION", "_default")
        return get_collection(alias=alias, scope=scope, collection=collection)

    def _get_key(self, session_key=None):
        """Return the Couchbase document key for a session."""
        return f"{SESSION_KEY_PREFIX}{session_key or self.session_key}"

    def _get_expiry_timedelta(self):
        """Return the session expiry as a timedelta for Couchbase TTL."""
        return timedelta(seconds=self.get_expiry_age())

    def load(self):
        """Load session data from Couchbase."""
        try:
            from couchbase.exceptions import DocumentNotFoundException

            collection = self._get_collection()
            result = collection.get(self._get_key())
            data = result.content_as[dict]
            return data.get("session_data", {})
        except DocumentNotFoundException:
            self._session_key = None
            return {}
        except Exception:
            logger.exception("Failed to load session (key redacted)")
            self._session_key = None
            return {}

    def exists(self, session_key):
        """Check if a session exists in Couchbase."""
        try:
            collection = self._get_collection()
            result = collection.exists(self._get_key(session_key))
            return result.exists
        except Exception:
            return False

    def create(self):
        """Create a new session in Couchbase.

        Generates a unique session key and saves it.
        """
        while True:
            self._session_key = self._get_new_session_key()
            try:
                self.save(must_create=True)
            except CreateError:
                continue
            self.modified = True
            return

    def save(self, must_create=False):
        """Save session data to Couchbase with TTL."""
        if self.session_key is None:
            return self.create()

        collection = self._get_collection()
        key = self._get_key()
        data = {
            "session_data": self._get_session(no_load=must_create),
            "session_key": self.session_key,
        }
        expiry = self._get_expiry_timedelta()

        try:
            if must_create:
                from couchbase.options import InsertOptions

                collection.insert(key, data, InsertOptions(expiry=expiry))
            else:
                from couchbase.options import UpsertOptions

                collection.upsert(key, data, UpsertOptions(expiry=expiry))
        except Exception as e:
            if must_create:
                from couchbase.exceptions import DocumentExistsException

                if isinstance(e, DocumentExistsException):
                    raise CreateError() from e
            raise

    def delete(self, session_key=None):
        """Delete a session from Couchbase."""
        if session_key is None:
            if self.session_key is None:
                return
            session_key = self.session_key

        try:
            from couchbase.exceptions import DocumentNotFoundException

            collection = self._get_collection()
            collection.remove(self._get_key(session_key))
        except DocumentNotFoundException:
            pass
        except Exception:
            logger.exception("Failed to delete session (key redacted)")

    @classmethod
    def clear_expired(cls):
        """Not needed — Couchbase TTL handles expiry automatically."""
