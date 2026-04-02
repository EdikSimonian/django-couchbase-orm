"""Tests for async QuerySet, Document CRUD, and Manager methods."""

import asyncio

import pytest
from django.test import override_settings

from django_couchbase_orm.document import Document
from django_couchbase_orm.fields.simple import IntegerField, StringField
from django_couchbase_orm.queryset.queryset import QuerySet


COUCHBASE_SETTINGS = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "admin",
        "PASSWORD": "password",
        "BUCKET": "testbucket",
        "SCOPE": "_default",
    }
}


class AsyncDoc(Document):
    name = StringField(required=True)
    score = IntegerField(default=0)

    class Meta:
        collection_name = "async_docs"


class TestAsyncQuerySetBuild:
    """Test that async methods build correct queries (no execution needed)."""

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_alist_returns_coroutine(self):
        qs = AsyncDoc.objects.filter(name="test")
        coro = qs.alist()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_acount_returns_coroutine(self):
        qs = AsyncDoc.objects.filter(name="test")
        coro = qs.acount()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_afirst_returns_coroutine(self):
        qs = AsyncDoc.objects.filter(name="test")
        coro = qs.afirst()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aget_returns_coroutine(self):
        qs = AsyncDoc.objects.filter(name="test")
        coro = qs.aget(name="test")
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aexists_returns_coroutine(self):
        qs = AsyncDoc.objects.filter(name="test")
        coro = qs.aexists()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_acount_uses_cache(self):
        """If result_cache is set, acount should return len without querying."""
        qs = AsyncDoc.objects.all()
        qs._result_cache = [1, 2, 3]

        result = asyncio.run(qs.acount())
        assert result == 3

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aexists_uses_cache(self):
        qs = AsyncDoc.objects.all()
        qs._result_cache = []
        result = asyncio.run(qs.aexists())
        assert result is False

        qs._result_cache = [1]
        result = asyncio.run(qs.aexists())
        assert result is True


class TestAsyncDocumentMethods:
    def test_asave_returns_coroutine(self):
        doc = AsyncDoc(name="test")
        coro = doc.asave()
        assert asyncio.iscoroutine(coro)
        coro.close()

    def test_adelete_returns_coroutine(self):
        doc = AsyncDoc(name="test")
        coro = doc.adelete()
        assert asyncio.iscoroutine(coro)
        coro.close()

    def test_areload_returns_coroutine(self):
        doc = AsyncDoc(name="test")
        coro = doc.areload()
        assert asyncio.iscoroutine(coro)
        coro.close()


class TestAsyncManagerMethods:
    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_acount_returns_coroutine(self):
        coro = AsyncDoc.objects.acount()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_afirst_returns_coroutine(self):
        coro = AsyncDoc.objects.afirst()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aget_no_args_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            asyncio.run(AsyncDoc.objects.aget())

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aget_pk_returns_coroutine(self):
        coro = AsyncDoc.objects.aget(pk="some-id")
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_acreate_returns_coroutine(self):
        coro = AsyncDoc.objects.acreate(name="test")
        assert asyncio.iscoroutine(coro)
        coro.close()

    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_alist_returns_coroutine(self):
        coro = AsyncDoc.objects.alist()
        assert asyncio.iscoroutine(coro)
        coro.close()


class TestAsyncIteration:
    @override_settings(COUCHBASE=COUCHBASE_SETTINGS)
    def test_aiter_support(self):
        """QuerySet should support async for."""
        qs = AsyncDoc.objects.all()
        assert hasattr(qs, "__aiter__")
