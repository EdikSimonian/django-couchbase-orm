"""Integration tests against a real local Couchbase instance.

Requires: docker run -d --name couchbase-test -p 8091-8097:8091-8097 -p 11210-11211:11210-11211 couchbase/server:latest

Skip with: pytest -m "not integration"
"""

import asyncio
import uuid

import pytest
from django.test import override_settings

from django_couchbase_orm.aggregates import Avg, Count, Max, Min, Sum
from django_couchbase_orm.connection import get_cluster, reset_connections
from django_couchbase_orm.document import Document
from django_couchbase_orm.exceptions import OperationError, ValidationError
from django_couchbase_orm.fields.compound import (
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    ListField,
)
from django_couchbase_orm.fields.datetime import DateTimeField
from django_couchbase_orm.fields.reference import ReferenceField
from django_couchbase_orm.fields.simple import (
    BooleanField,
    FloatField,
    IntegerField,
    StringField,
)
from django_couchbase_orm.paginator import CouchbasePaginator
from django_couchbase_orm.queryset.q import Q
from django_couchbase_orm.signals import post_delete, post_save, pre_save

LOCAL_COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "testbucket",
        "SCOPE": "_default",
    }
}

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


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _couchbase_available(),
        reason="Local Couchbase not available",
    ),
]


# ============================================================
# Test Document definitions
# ============================================================


class Address(EmbeddedDocument):
    city = StringField(required=True)
    state = StringField()


class IntBrewer(Document):
    name = StringField(required=True)
    city = StringField()
    country = StringField()
    tags = ListField(field=StringField())
    address = EmbeddedDocumentField(Address)
    meta_info = DictField()
    active = BooleanField(default=True)
    created = DateTimeField(auto_now_add=True)
    updated = DateTimeField(auto_now=True)

    class Meta:
        collection_name = "_default"
        doc_type_field = "_type"


class IntBeer(Document):
    name = StringField(required=True)
    abv = FloatField()
    ibu = IntegerField()
    style = StringField()
    brewery = ReferenceField(IntBrewer)

    class Meta:
        collection_name = "_default"
        doc_type_field = "_type"


def _uid():
    return f"test_{uuid.uuid4().hex[:12]}"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _use_local_couchbase(settings):
    settings.COUCHBASE = LOCAL_COUCHBASE
    reset_connections()
    yield
    reset_connections()


@pytest.fixture
def brewer_ids():
    """Track created document IDs for cleanup."""
    ids = []
    yield ids
    # Cleanup
    try:
        cluster = get_cluster()
        coll = cluster.bucket("testbucket").default_collection()
        for doc_id in ids:
            try:
                coll.remove(doc_id)
            except Exception:
                pass
    except Exception:
        pass


# ============================================================
# Document CRUD
# ============================================================


class TestIntegrationCRUD:
    def test_save_and_get(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Test Brewery", city="Portland", country="US")
        b.save()
        assert b._is_new is False
        assert b._cas is not None

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.name == "Test Brewery"
        assert loaded.city == "Portland"

    def test_update(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Original")
        b.save()

        b._data["name"] = "Updated"
        b.save()

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.name == "Updated"

    def test_delete(self, brewer_ids):
        doc_id = _uid()

        b = IntBrewer(_id=doc_id, name="ToDelete")
        b.save()
        b.delete()

        with pytest.raises(IntBrewer.DoesNotExist):
            IntBrewer.objects.get(pk=doc_id)

    def test_reload(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Before")
        b.save()

        # Modify directly
        cluster = get_cluster()
        coll = cluster.bucket("testbucket").default_collection()
        coll.upsert(doc_id, {**b.to_dict(), "name": "After"})

        b.reload()
        assert b.name == "After"

    def test_create_via_manager(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer.objects.create(_id=doc_id, name="Created")
        assert b._is_new is False
        assert b.pk == doc_id

    def test_get_or_create(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b1, created1 = IntBrewer.objects.get_or_create(_id=doc_id, defaults={"name": "New"})
        assert created1 is True

        b2, created2 = IntBrewer.objects.get_or_create(_id=doc_id)
        assert created2 is False
        assert b2.name == "New"

    def test_exists(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        assert IntBrewer.objects.exists(doc_id) is False
        IntBrewer(_id=doc_id, name="test").save()
        assert IntBrewer.objects.exists(doc_id) is True

    def test_validation_prevents_save(self):
        b = IntBrewer()  # name is required
        with pytest.raises(ValidationError):
            b.save()


# ============================================================
# QuerySet (N1QL)
# ============================================================


class TestIntegrationQuerySet:
    @pytest.fixture(autouse=True)
    def _create_test_data(self, brewer_ids):
        """Create test breweries for query tests."""
        self.ids = []
        for i, (name, city, country) in enumerate([
            ("Alpha Brewing", "Portland", "US"),
            ("Beta Brewing", "Seattle", "US"),
            ("Gamma Brewing", "Vancouver", "Canada"),
            ("Delta Brewing", "Portland", "US"),
            ("Epsilon Brewing", "London", "UK"),
        ]):
            doc_id = f"test_qs_{uuid.uuid4().hex[:8]}"
            b = IntBrewer(_id=doc_id, name=name, city=city, country=country)
            b.save()
            self.ids.append(doc_id)
            brewer_ids.append(doc_id)

        # Wait for indexing
        import time
        time.sleep(1)

    def test_filter(self):
        results = list(IntBrewer.objects.filter(country="US").order_by("name"))
        names = [r.name for r in results]
        assert "Alpha Brewing" in names
        assert "Beta Brewing" in names

    def test_filter_icontains(self):
        results = list(IntBrewer.objects.filter(name__icontains="alpha"))
        assert any(r.name == "Alpha Brewing" for r in results)

    def test_exclude(self):
        results = list(IntBrewer.objects.filter(country="US").exclude(city="Portland"))
        names = [r.name for r in results]
        assert "Beta Brewing" in names
        assert "Alpha Brewing" not in names

    def test_count(self):
        count = IntBrewer.objects.filter(country="US").count()
        assert count >= 3  # At least our 3 US breweries

    def test_exists(self):
        assert IntBrewer.objects.filter(country="US").exists()
        assert not IntBrewer.objects.filter(country="Atlantis").exists()

    def test_first(self):
        doc = IntBrewer.objects.filter(country="UK").first()
        assert doc is not None
        assert doc.name == "Epsilon Brewing"

    def test_order_by(self):
        results = list(IntBrewer.objects.filter(country="US").order_by("name"))
        names = [r.name for r in results if r.pk in self.ids]
        assert names == sorted(names)

    def test_slice(self):
        results = list(IntBrewer.objects.filter(country="US").order_by("name")[:2])
        assert len(results) == 2

    def test_q_objects(self):
        results = list(IntBrewer.objects.filter(Q(city="Portland") | Q(city="London")))
        cities = {r.city for r in results}
        assert "Portland" in cities
        assert "London" in cities

    def test_get_by_field(self):
        doc = IntBrewer.objects.get(name="Epsilon Brewing")
        assert doc.country == "UK"

    def test_get_not_found(self):
        with pytest.raises(IntBrewer.DoesNotExist):
            IntBrewer.objects.get(name="Nonexistent Brewery XYZ999")

    def test_values(self):
        results = list(IntBrewer.objects.filter(country="UK").values("name", "city"))
        assert len(results) >= 1
        assert "name" in results[0]

    def test_iterator(self):
        count = 0
        for doc in IntBrewer.objects.filter(country="US").iterator():
            count += 1
        assert count >= 3


# ============================================================
# Aggregation
# ============================================================


class TestIntegrationAggregation:
    @pytest.fixture(autouse=True)
    def _create_beers(self, brewer_ids):
        self.beer_ids = []
        for name, abv in [("IPA", 6.5), ("Stout", 5.0), ("Lager", 4.5), ("DIPA", 8.5)]:
            doc_id = f"test_beer_{uuid.uuid4().hex[:8]}"
            IntBeer(_id=doc_id, name=name, abv=abv, style="Ale").save()
            self.beer_ids.append(doc_id)
            brewer_ids.append(doc_id)

        import time
        time.sleep(1)

    def test_aggregate_avg(self):
        result = IntBeer.objects.filter(style="Ale").aggregate(avg_abv=Avg("abv"))
        assert result["avg_abv"] is not None
        assert 4.0 < result["avg_abv"] < 9.0

    def test_aggregate_count(self):
        result = IntBeer.objects.filter(style="Ale").aggregate(total=Count("*"))
        assert result["total"] >= 4

    def test_aggregate_min_max(self):
        result = IntBeer.objects.filter(style="Ale").aggregate(
            min_abv=Min("abv"), max_abv=Max("abv")
        )
        assert result["min_abv"] <= result["max_abv"]


# ============================================================
# Pagination
# ============================================================


class TestIntegrationPagination:
    @pytest.fixture(autouse=True)
    def _create_data(self, brewer_ids):
        for i in range(15):
            doc_id = f"test_page_{uuid.uuid4().hex[:8]}"
            IntBrewer(_id=doc_id, name=f"Paginator Brewery {i:02d}", country="PG").save()
            brewer_ids.append(doc_id)

        import time
        time.sleep(1)

    def test_paginator(self):
        qs = IntBrewer.objects.filter(country="PG").order_by("name")
        paginator = CouchbasePaginator(qs, per_page=5)
        assert paginator.count >= 15
        assert paginator.num_pages >= 3

        page1 = paginator.page(1)
        assert len(page1) == 5
        assert page1.has_next
        assert not page1.has_previous


# ============================================================
# Compound Fields
# ============================================================


class TestIntegrationCompoundFields:
    def test_list_field(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Tagged", tags=["craft", "organic", "local"])
        b.save()

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.tags == ["craft", "organic", "local"]

    def test_embedded_document(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(
            _id=doc_id,
            name="Embedded",
            address=Address(city="Portland", state="OR"),
        )
        b.save()

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.address.city == "Portland"
        assert loaded.address.state == "OR"

    def test_dict_field(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="WithMeta", meta_info={"founded": 2020, "rating": 4.5})
        b.save()

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.meta_info["founded"] == 2020


# ============================================================
# ReferenceField
# ============================================================


class TestIntegrationReference:
    def test_reference_save_and_load(self, brewer_ids):
        brew_id = _uid()
        beer_id = _uid()
        brewer_ids.extend([brew_id, beer_id])

        brewery = IntBrewer(_id=brew_id, name="Ref Brewery")
        brewery.save()

        beer = IntBeer(_id=beer_id, name="Ref IPA", abv=7.0, brewery=brew_id)
        beer.save()

        loaded = IntBeer.objects.get(pk=beer_id)
        assert loaded.brewery == brew_id

        # Dereference
        field = IntBeer._meta.fields["brewery"]
        ref_brewery = field.dereference(loaded.brewery)
        assert ref_brewery.name == "Ref Brewery"

    def test_select_related(self, brewer_ids):
        brew_id = _uid()
        beer_ids = []
        brewer_ids.append(brew_id)

        brewery = IntBrewer(_id=brew_id, name="SR Brewery")
        brewery.save()

        for i in range(3):
            bid = _uid()
            IntBeer(_id=bid, name=f"SR Beer {i}", brewery=brew_id).save()
            beer_ids.append(bid)
            brewer_ids.append(bid)

        import time
        time.sleep(1)

        beers = list(IntBeer.objects.select_related("brewery").filter(brewery=brew_id))
        assert len(beers) >= 3
        for beer in beers:
            assert beer._prefetched["brewery"].name == "SR Brewery"


# ============================================================
# Signals
# ============================================================


class TestIntegrationSignals:
    def test_pre_save_fires(self, brewer_ids):
        calls = []

        def handler(sender, instance, **kwargs):
            calls.append(instance.name)

        pre_save.connect(handler, sender=IntBrewer)
        try:
            doc_id = _uid()
            brewer_ids.append(doc_id)
            IntBrewer(_id=doc_id, name="SignalTest").save()
            assert "SignalTest" in calls
        finally:
            pre_save.disconnect(handler, sender=IntBrewer)


# ============================================================
# Sub-document Operations
# ============================================================


class TestIntegrationSubDoc:
    def test_subdoc_upsert_and_get(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="SubDoc Test")
        b.save()

        b.subdoc.upsert("extra_field", "hello")
        val = b.subdoc.get("extra_field")
        assert val == "hello"

    def test_subdoc_array_ops(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Array Test", tags=["a"])
        b.save()

        b.subdoc.array_append("tags", "b")
        b.reload()
        assert "b" in b.tags

    def test_subdoc_increment(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Counter Test")
        b.save()

        b.subdoc.upsert("visit_count", 0)
        b.subdoc.increment("visit_count", 5)
        val = b.subdoc.get("visit_count")
        assert val == 5

    def test_subdoc_remove(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Remove Test")
        b.save()
        b.subdoc.upsert("temp", "value")
        b.subdoc.remove("temp")
        assert b.subdoc.exists("temp") is False


# ============================================================
# Auto Timestamps
# ============================================================


class TestIntegrationTimestamps:
    def test_auto_now_add(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Timestamps")
        b.save()

        loaded = IntBrewer.objects.get(pk=doc_id)
        assert loaded.created is not None

    def test_auto_now(self, brewer_ids):
        doc_id = _uid()
        brewer_ids.append(doc_id)

        b = IntBrewer(_id=doc_id, name="Timestamps")
        b.save()
        first_updated = b.updated

        import time
        time.sleep(0.1)
        b._data["name"] = "Updated"
        b.save()

        assert b.updated >= first_updated


# ============================================================
# Bulk Operations
# ============================================================


class TestIntegrationBulk:
    def test_bulk_create(self, brewer_ids):
        docs = []
        for i in range(5):
            doc_id = _uid()
            brewer_ids.append(doc_id)
            docs.append(IntBrewer(_id=doc_id, name=f"Bulk {i}"))

        result = IntBrewer.objects.bulk_create(docs)
        assert len(result) == 5
        for doc in result:
            assert doc._is_new is False

    def test_bulk_update(self, brewer_ids):
        docs = []
        for i in range(3):
            doc_id = _uid()
            brewer_ids.append(doc_id)
            docs.append(IntBrewer(_id=doc_id, name=f"BulkUp {i}", city="OldCity"))

        IntBrewer.objects.bulk_create(docs)

        for doc in docs:
            doc._data["city"] = "NewCity"

        updated = IntBrewer.objects.bulk_update(docs, ["city"])
        assert updated == 3

        for doc in docs:
            loaded = IntBrewer.objects.get(pk=doc.pk)
            assert loaded.city == "NewCity"


# Note: Async integration tests are skipped here because acouchbase's event loop
# conflicts with pytest-asyncio. Async operations are covered by mocked tests in
# test_async.py and test_async_execution.py. The sync integration tests above
# verify that the generated N1QL and KV operations are correct against the real DB.
