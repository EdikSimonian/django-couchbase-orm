"""Tests for bulk_create and bulk_update."""

import pytest

from django_couchbase_orm.document import Document
from django_couchbase_orm.exceptions import OperationError, ValidationError
from django_couchbase_orm.fields.simple import IntegerField, StringField


class BulkDoc(Document):
    name = StringField(required=True)
    score = IntegerField(default=0)

    class Meta:
        collection_name = "bulk_docs"


class TestBulkCreate:
    def test_basic(self, patch_collection):
        docs = [
            BulkDoc(name="Alice", score=10),
            BulkDoc(name="Bob", score=20),
            BulkDoc(name="Carol", score=30),
        ]
        result = BulkDoc.objects.bulk_create(docs)
        assert len(result) == 3
        for doc in result:
            assert doc._is_new is False
            assert doc._cas is not None
            assert doc.pk in patch_collection._store

    def test_validates(self, patch_collection):
        docs = [
            BulkDoc(name="Valid"),
            BulkDoc(),  # name is required
        ]
        with pytest.raises(ValidationError):
            BulkDoc.objects.bulk_create(docs)
        # Nothing should have been saved
        assert len(patch_collection._store) == 0

    def test_data_persisted(self, patch_collection):
        docs = [BulkDoc(name="Test", score=99)]
        BulkDoc.objects.bulk_create(docs)
        stored = patch_collection._store[docs[0].pk]
        assert stored["name"] == "Test"
        assert stored["score"] == 99

    def test_empty_list(self, patch_collection):
        result = BulkDoc.objects.bulk_create([])
        assert result == []


class TestBulkUpdate:
    def test_basic(self, patch_collection):
        # Create documents first
        docs = [
            BulkDoc(name="Alice", score=10),
            BulkDoc(name="Bob", score=20),
        ]
        BulkDoc.objects.bulk_create(docs)

        # Modify and bulk update
        docs[0]._data["score"] = 100
        docs[1]._data["score"] = 200

        patch_collection.mutate_in = lambda key, specs, *a, **kw: type("R", (), {"cas": 1})()  # mock subdoc

        updated = BulkDoc.objects.bulk_update(docs, ["score"])
        assert updated == 2

    def test_empty_docs(self, patch_collection):
        assert BulkDoc.objects.bulk_update([], ["score"]) == 0

    def test_empty_fields(self, patch_collection):
        docs = [BulkDoc(name="Test")]
        assert BulkDoc.objects.bulk_update(docs, []) == 0

    def test_unknown_field_raises(self, patch_collection):
        docs = [BulkDoc(name="Test")]
        BulkDoc.objects.bulk_create(docs)
        patch_collection.mutate_in = lambda key, specs, *a, **kw: type("R", (), {"cas": 1})()
        with pytest.raises(OperationError):
            BulkDoc.objects.bulk_update(docs, ["nonexistent_field"])
