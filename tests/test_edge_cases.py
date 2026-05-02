"""Comprehensive edge-case tests for django-couchbase-orm.

These tests cover boundary conditions, type coercion, null handling,
return types, and other edge cases that can hide bugs when mocked.

Tests are split into two groups:
- Unit tests: No Couchbase required (field validation, serialization, etc.)
- Integration tests: Require a running Couchbase instance
"""

import datetime
import uuid

import pytest

from django_couchbase_orm.document import Document
from django_couchbase_orm.exceptions import OperationError, ValidationError
from django_couchbase_orm.fields.base import BaseField
from django_couchbase_orm.fields.compound import (
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    ListField,
)
from django_couchbase_orm.fields.simple import (
    BooleanField,
    FloatField,
    IntegerField,
    StringField,
    UUIDField,
)
from tests.conftest import couchbase_available, flush_collection

# ============================================================
# Unit tests — no Couchbase required
# ============================================================


class TestBaseFieldDefaults:
    """Test BaseField.has_default() and get_default() edge cases."""

    def test_has_default_with_none(self):
        """has_default() returns False for default=None, which is the sentinel."""
        f = BaseField(default=None)
        assert f.has_default() is False

    def test_has_default_with_zero(self):
        f = BaseField(default=0)
        assert f.has_default() is True

    def test_has_default_with_false(self):
        f = BaseField(default=False)
        assert f.has_default() is True

    def test_has_default_with_empty_string(self):
        f = BaseField(default="")
        assert f.has_default() is True

    def test_has_default_with_empty_list(self):
        f = BaseField(default=[])
        assert f.has_default() is True

    def test_get_default_callable(self):
        f = BaseField(default=list)
        d1 = f.get_default()
        d2 = f.get_default()
        assert d1 == []
        assert d2 == []
        assert d1 is not d2  # Each call returns new instance

    def test_get_default_mutable_deepcopy(self):
        """Mutable defaults should be deep-copied to prevent shared state."""
        original = [1, 2, 3]
        f = BaseField(default=original)
        d = f.get_default()
        d.append(4)
        assert original == [1, 2, 3]  # Original unchanged


class TestStringFieldValidation:
    def test_empty_string_valid(self):
        f = StringField()
        f.name = "test"
        f.validate("")  # Should not raise

    def test_min_length_boundary(self):
        f = StringField(min_length=3)
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate("ab")
        f.validate("abc")  # Exactly at boundary

    def test_max_length_boundary(self):
        f = StringField(max_length=5)
        f.name = "test"
        f.validate("abcde")  # Exactly at boundary
        with pytest.raises(ValidationError):
            f.validate("abcdef")

    def test_unicode_string(self):
        f = StringField()
        f.name = "test"
        f.validate("日本語テスト")
        assert f.to_json("日本語テスト") == "日本語テスト"

    def test_to_python_non_string(self):
        f = StringField()
        f.name = "test"
        assert f.to_python(123) == "123"
        assert f.to_python(True) == "True"

    def test_regex_validation(self):
        f = StringField(regex=r"^[a-z]+$")
        f.name = "test"
        f.validate("abc")
        with pytest.raises(ValidationError):
            f.validate("ABC")
        with pytest.raises(ValidationError):
            f.validate("abc123")


class TestIntegerFieldValidation:
    def test_boolean_rejected(self):
        """Booleans are ints in Python but should be rejected by IntegerField."""
        f = IntegerField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate(True)
        with pytest.raises(ValidationError):
            f.validate(False)

    def test_zero_valid(self):
        f = IntegerField()
        f.name = "test"
        f.validate(0)

    def test_negative_valid(self):
        f = IntegerField()
        f.name = "test"
        f.validate(-999)

    def test_min_value_boundary(self):
        f = IntegerField(min_value=0)
        f.name = "test"
        f.validate(0)
        with pytest.raises(ValidationError):
            f.validate(-1)

    def test_max_value_boundary(self):
        f = IntegerField(max_value=100)
        f.name = "test"
        f.validate(100)
        with pytest.raises(ValidationError):
            f.validate(101)

    def test_to_python_string_int(self):
        f = IntegerField()
        f.name = "test"
        assert f.to_python("42") == 42

    def test_to_python_invalid_string(self):
        f = IntegerField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.to_python("not_a_number")

    def test_large_integer(self):
        f = IntegerField()
        f.name = "test"
        large = 2**53
        f.validate(large)
        assert f.to_json(large) == large


class TestFloatFieldValidation:
    def test_boolean_rejected(self):
        f = FloatField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate(True)

    def test_integer_accepted(self):
        """IntegerField rejects bool, but FloatField should accept plain int."""
        f = FloatField()
        f.name = "test"
        f.validate(42)  # int is acceptable as a float

    def test_nan_and_infinity(self):
        f = FloatField()
        f.name = "test"
        # NaN and Infinity are valid floats but not JSON-safe
        f.validate(float("nan"))
        f.validate(float("inf"))
        f.validate(float("-inf"))

    def test_to_python_string_float(self):
        f = FloatField()
        f.name = "test"
        assert f.to_python("3.14") == 3.14


class TestBooleanFieldValidation:
    def test_non_bool_rejected(self):
        f = BooleanField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate(1)
        with pytest.raises(ValidationError):
            f.validate("true")
        with pytest.raises(ValidationError):
            f.validate(0)

    def test_to_python_truthy(self):
        f = BooleanField()
        assert f.to_python(1) is True
        assert f.to_python("") is False
        assert f.to_python(0) is False


class TestUUIDField:
    def test_auto_generates_uuid(self):
        f = UUIDField(auto=True)
        d = f.get_default()
        assert isinstance(d, uuid.UUID)

    def test_auto_unique(self):
        f = UUIDField(auto=True)
        uuids = {f.get_default() for _ in range(100)}
        assert len(uuids) == 100

    def test_string_to_uuid(self):
        f = UUIDField()
        f.name = "test"
        uid = "12345678-1234-5678-1234-567812345678"
        result = f.to_python(uid)
        assert isinstance(result, uuid.UUID)
        assert str(result) == uid

    def test_invalid_uuid_string(self):
        f = UUIDField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.to_python("not-a-uuid")

    def test_to_json_returns_string(self):
        f = UUIDField()
        f.name = "test"
        uid = uuid.uuid4()
        result = f.to_json(uid)
        assert isinstance(result, str)
        assert result == str(uid)


class TestListFieldValidation:
    def test_empty_list_valid(self):
        f = ListField()
        f.name = "test"
        f.validate([])

    def test_min_length(self):
        f = ListField(min_length=2)
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate([1])
        f.validate([1, 2])

    def test_max_length(self):
        f = ListField(max_length=3)
        f.name = "test"
        f.validate([1, 2, 3])
        with pytest.raises(ValidationError):
            f.validate([1, 2, 3, 4])

    def test_typed_list_validation(self):
        f = ListField(field=IntegerField())
        f.name = "test"
        f.validate([1, 2, 3])
        with pytest.raises(ValidationError):
            f.validate([1, "not_int", 3])

    def test_tuple_accepted(self):
        f = ListField()
        f.name = "test"
        f.validate((1, 2, 3))

    def test_to_json_preserves_element_types(self):
        f = ListField(field=IntegerField())
        f.name = "test"
        result = f.to_json([1, 2, 3])
        assert result == [1, 2, 3]

    def test_non_list_rejected(self):
        f = ListField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate("not a list")
        with pytest.raises(ValidationError):
            f.validate(123)


class TestDictFieldValidation:
    def test_empty_dict_valid(self):
        f = DictField()
        f.name = "test"
        f.validate({})

    def test_non_dict_rejected(self):
        f = DictField()
        f.name = "test"
        with pytest.raises(ValidationError):
            f.validate([1, 2])
        with pytest.raises(ValidationError):
            f.validate("string")

    def test_nested_dict(self):
        f = DictField()
        f.name = "test"
        nested = {"a": {"b": {"c": 1}}}
        f.validate(nested)
        assert f.to_json(nested) == nested

    def test_to_python_returns_copy(self):
        f = DictField()
        f.name = "test"
        original = {"key": "value"}
        result = f.to_python(original)
        result["key"] = "modified"
        assert original["key"] == "value"


class TestEmbeddedDocument:
    def test_unexpected_field_rejected(self):
        class Addr(EmbeddedDocument):
            city = StringField()

        with pytest.raises(TypeError, match="Unexpected field"):
            Addr(city="NYC", nonexistent="value")

    def test_defaults_applied(self):
        class Cfg(EmbeddedDocument):
            retries = IntegerField(default=3)
            verbose = BooleanField(default=False)

        cfg = Cfg()
        assert cfg.retries == 3
        assert cfg.verbose is False

    def test_nested_embedded_document(self):
        class Inner(EmbeddedDocument):
            value = IntegerField()

        class Outer(EmbeddedDocument):
            inner = EmbeddedDocumentField(Inner)

        outer = Outer(inner=Inner(value=42))
        d = outer.to_dict()
        assert d == {"inner": {"value": 42}}

    def test_from_dict_roundtrip(self):
        class Addr(EmbeddedDocument):
            city = StringField()
            zip_code = StringField()

        addr = Addr(city="NYC", zip_code="10001")
        d = addr.to_dict()
        addr2 = Addr.from_dict(d)
        assert addr == addr2

    def test_validate_required_field(self):
        class Strict(EmbeddedDocument):
            name = StringField(required=True)

        s = Strict()
        with pytest.raises(ValidationError):
            s.validate()


class TestDocumentEdgeCases:
    """Test Document class behavior without Couchbase."""

    def test_unexpected_kwargs_rejected(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        with pytest.raises(TypeError, match="Unexpected keyword arguments"):
            MyDoc(name="test", nonexistent="value")

    def test_document_equality(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        d1 = MyDoc(_id="same", name="a")
        d2 = MyDoc(_id="same", name="b")
        d3 = MyDoc(_id="different", name="a")
        assert d1 == d2  # Same ID = equal
        assert d1 != d3  # Different ID

    def test_document_hash(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        d1 = MyDoc(_id="x", name="a")
        d2 = MyDoc(_id="x", name="b")
        assert hash(d1) == hash(d2)
        s = {d1, d2}
        assert len(s) == 1

    def test_to_dict_skips_none_optional_fields(self):
        class MyDoc(Document):
            name = StringField(required=True)
            bio = StringField(required=False)

            class Meta:
                collection_name = "test"

        doc = MyDoc(name="Alice")
        d = doc.to_dict()
        assert "name" in d
        assert d["name"] == "Alice"
        # Optional None field is not in dict
        assert "bio" not in d

    def test_to_dict_includes_none_required_fields(self):
        class MyDoc(Document):
            name = StringField(required=True)

            class Meta:
                collection_name = "test"

        doc = MyDoc()  # name defaults to None
        d = doc.to_dict()
        assert "name" in d
        assert d["name"] is None

    def test_full_clean_required_field_missing(self):
        class MyDoc(Document):
            name = StringField(required=True)

            class Meta:
                collection_name = "test"

        doc = MyDoc()
        with pytest.raises(ValidationError):
            doc.full_clean()

    def test_full_clean_multiple_errors(self):
        class MyDoc(Document):
            name = StringField(required=True)
            age = IntegerField(required=True)

            class Meta:
                collection_name = "test"

        doc = MyDoc()
        with pytest.raises(ValidationError) as exc_info:
            doc.full_clean()
        # Should report both errors
        assert exc_info.value.errors is not None
        assert len(exc_info.value.errors) == 2

    def test_pk_property(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        doc = MyDoc(_id="my-id", name="test")
        assert doc.pk == "my-id"
        doc.pk = "new-id"
        assert doc._id == "new-id"

    def test_document_repr(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        doc = MyDoc(_id="abc", name="test")
        assert "MyDoc" in repr(doc)
        assert "abc" in repr(doc)

    def test_choices_validation(self):
        class MyDoc(Document):
            status = StringField(choices=["active", "inactive"])

            class Meta:
                collection_name = "test"

        doc = MyDoc(status="active")
        doc.full_clean()

        doc2 = MyDoc(status="unknown")
        with pytest.raises(ValidationError):
            doc2.full_clean()

    def test_custom_db_field(self):
        class MyDoc(Document):
            full_name = StringField(db_field="fn")

            class Meta:
                collection_name = "test"

        doc = MyDoc(full_name="Alice")
        d = doc.to_dict()
        assert "fn" in d
        assert d["fn"] == "Alice"
        assert "full_name" not in d

    def test_from_dict_with_db_field(self):
        class MyDoc(Document):
            full_name = StringField(db_field="fn")

            class Meta:
                collection_name = "test"

        doc = MyDoc.from_dict("key1", {"fn": "Alice"})
        assert doc.full_name == "Alice"
        assert doc._id == "key1"
        assert doc._is_new is False

    def test_custom_validators(self):
        def must_be_positive(value):
            if value <= 0:
                raise ValidationError("Must be positive")

        class MyDoc(Document):
            count = IntegerField(validators=[must_be_positive])

            class Meta:
                collection_name = "test"

        doc = MyDoc(count=5)
        doc.full_clean()

        doc2 = MyDoc(count=-1)
        with pytest.raises(ValidationError):
            doc2.full_clean()

    def test_is_new_flag(self):
        class MyDoc(Document):
            name = StringField()

            class Meta:
                collection_name = "test"

        doc = MyDoc(name="test")
        assert doc._is_new is True

    def test_document_setattr(self):
        class MyDoc(Document):
            name = StringField()
            age = IntegerField()

            class Meta:
                collection_name = "test"

        doc = MyDoc(name="Alice", age=30)
        doc.name = "Bob"
        doc.age = 25
        assert doc.name == "Bob"
        assert doc.age == 25
        assert doc._data["name"] == "Bob"


class TestCursorHelpers:
    """Test cursor helper functions."""

    def test_parse_select_columns_with_distinct(self):
        from django_couchbase_orm.db.backends.couchbase.cursor import _parse_select_columns

        sql = "SELECT DISTINCT `name`, `age` FROM `b`.`s`.`t`"
        cols = _parse_select_columns(sql)
        assert cols == ["name", "age"]

    def test_parse_select_columns_aggregates(self):
        from django_couchbase_orm.db.backends.couchbase.cursor import _parse_select_columns

        sql = "SELECT COUNT(*) AS `__count` FROM `b`.`s`.`t`"
        cols = _parse_select_columns(sql)
        assert cols == ["__count"]

    def test_collapse_in_clauses_no_in(self):
        from django_couchbase_orm.db.backends.couchbase.cursor import CouchbaseCursor

        sql = "SELECT * FROM t WHERE x = %s"
        params = ["a"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == sql
        assert new_params == params

    def test_collapse_in_clauses_multiple(self):
        from django_couchbase_orm.db.backends.couchbase.cursor import CouchbaseCursor

        sql = "SELECT * FROM t WHERE x IN (%s, %s) AND y IN (%s)"
        params = ["a", "b", "c"]
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, params)
        assert new_sql == "SELECT * FROM t WHERE x IN %s AND y IN %s"
        assert new_params == [["a", "b"], ["c"]]


class TestOperationsDateHandling:
    """Test date/time adaptation edge cases."""

    def test_adapt_datefield_none(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.adapt_datefield_value(None) is None

    def test_adapt_datefield_string_passthrough(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.adapt_datefield_value("2024-01-15") == "2024-01-15"

    def test_adapt_datefield_date_object(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        result = ops.adapt_datefield_value(datetime.date(2024, 1, 15))
        assert result == "2024-01-15"

    def test_adapt_datetimefield_none(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.adapt_datetimefield_value(None) is None

    def test_adapt_datetimefield_naive(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        result = ops.adapt_datetimefield_value(dt)
        assert "2024-01-15" in result
        assert "10:30:00" in result

    @pytest.mark.parametrize("use_tz", [True])
    def test_adapt_datetimefield_naive_with_use_tz(self, use_tz, settings):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        settings.USE_TZ = use_tz
        ops = DatabaseOperations.__new__(DatabaseOperations)
        dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        result = ops.adapt_datetimefield_value(dt)
        assert "2024-01-15" in result
        assert "10:30:00" in result
        # With USE_TZ=True, naive datetimes get UTC offset.
        assert "+00:00" in result

    def test_adapt_datetimefield_aware_preserves_utc(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        tz = datetime.timezone(datetime.timedelta(hours=5))
        dt = datetime.datetime(2024, 1, 15, 15, 30, 0, tzinfo=tz)  # 15:30 +05:00 = 10:30 UTC
        result = ops.adapt_datetimefield_value(dt)
        assert "10:30:00" in result
        assert "+00:00" in result  # Stored as UTC with offset

    def test_adapt_decimalfield(self):
        from decimal import Decimal

        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        # Decimals are now serialized as strings to preserve precision.
        assert ops.adapt_decimalfield_value(Decimal("3.14")) == "3.14"
        assert ops.adapt_decimalfield_value(None) is None
        # High-precision value survives the round-trip exactly.
        big = Decimal("1234567890.123456789012345")
        assert ops.adapt_decimalfield_value(big) == "1234567890.123456789012345"


class TestConvertIntegerFieldValue:
    """Test integer field value conversion edge cases."""

    def test_none_returns_none(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.convert_integerfield_value(None, None, None) is None

    def test_string_int(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.convert_integerfield_value("42", None, None) == 42

    def test_empty_list_returns_none(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.convert_integerfield_value([], None, None) is None

    def test_single_element_list(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.convert_integerfield_value([42], None, None) == 42

    def test_multi_element_list(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        result = ops.convert_integerfield_value([1, 2, 3], None, None)
        assert result == [1, 2, 3]

    def test_invalid_string_fallback(self):
        from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        # Returns original value when conversion fails (could be considered a bug)
        result = ops.convert_integerfield_value("not_a_number", None, None)
        assert result == "not_a_number"


class TestCompilerSQLGeneration:
    """Test SQL generation without executing against Couchbase."""

    def test_quote_name(self):
        from django.db import connection

        assert connection.ops.quote_name("table") == "`table`"

    def test_quote_name_already_quoted(self):
        from django.db import connection

        assert connection.ops.quote_name("`table`") == "`table`"

    def test_sql_flush_empty_tables(self):
        from django.db import connection

        result = connection.ops.sql_flush(None, [])
        assert result == []

    def test_sql_flush_generates_delete(self):
        from django.db import connection

        result = connection.ops.sql_flush(None, ["test_table"])
        assert len(result) == 1
        assert "DELETE FROM" in result[0]


# ============================================================
# Integration tests — require Couchbase
# ============================================================


LOCAL_COUCHBASE = {
    "default": {
        "CONNECTION_STRING": "couchbase://localhost",
        "USERNAME": "Administrator",
        "PASSWORD": "password",
        "BUCKET": "testbucket",
        "SCOPE": "_default",
    }
}


class EdgeDoc(Document):
    name = StringField(required=True)
    age = IntegerField()
    score = FloatField()
    tags = ListField(field=StringField())
    active = BooleanField(default=True)
    metadata = DictField()

    class Meta:
        collection_name = "edge_test_docs"


integration_mark = pytest.mark.skipif(not couchbase_available, reason="Local Couchbase not available")


def _flush_edge_docs():
    flush_collection("edge_test_docs")


@integration_mark
class TestUpdateReturnTypes:
    """Regression tests: all mutation operations must return correct types."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_update_returns_int(self):
        EdgeDoc(name="old", age=1).save()
        count = EdgeDoc.objects.filter(name="old").update(name="new")
        assert isinstance(count, int)
        assert count == 1

    def test_update_no_match_returns_zero(self):
        count = EdgeDoc.objects.filter(name="nonexistent").update(name="new")
        assert isinstance(count, int)
        assert count == 0

    def test_update_multiple_fields(self):
        EdgeDoc(name="test", age=10, score=1.0).save()
        count = EdgeDoc.objects.filter(name="test").update(age=20, score=2.0)
        assert count == 1
        doc = EdgeDoc.objects.get(name="test")
        assert doc.age == 20
        assert doc.score == 2.0

    def test_update_multiple_docs(self):
        for i in range(5):
            EdgeDoc(name="batch", age=i).save()
        count = EdgeDoc.objects.filter(name="batch").update(name="updated")
        assert count == 5

    def test_delete_returns_int(self):
        EdgeDoc(name="del1", age=1).save()
        EdgeDoc(name="del2", age=2).save()
        count = EdgeDoc.objects.filter(name__in=["del1", "del2"]).delete()
        assert isinstance(count, int)
        assert count == 2

    def test_delete_no_match_returns_zero(self):
        count = EdgeDoc.objects.filter(name="nonexistent").delete()
        assert isinstance(count, int)
        assert count == 0


@integration_mark
class TestSaveUpdateCycles:
    """Test save-then-update cycles that exercise the full ORM path."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_save_then_modify_then_save(self):
        doc = EdgeDoc(name="original", age=10)
        doc.save()
        assert doc._is_new is False

        doc.name = "modified"
        doc.save()
        assert doc._is_new is False

        reloaded = EdgeDoc.objects.get(pk=doc.pk)
        assert reloaded.name == "modified"

    def test_save_then_reload(self):
        doc = EdgeDoc(name="test", age=25, score=3.14)
        doc.save()

        doc.name = "local_only"  # Not saved yet
        doc.reload()
        assert doc.name == "test"  # Reverted to saved state

    def test_save_then_bulk_update_then_reload(self):
        doc = EdgeDoc(name="before_unique_xyz", age=10)
        doc.save()

        count = EdgeDoc.objects.filter(name="before_unique_xyz").update(name="after_unique_xyz")
        assert count == 1

        doc.reload()
        assert doc.name == "after_unique_xyz"

    def test_cas_updated_on_save(self):
        doc = EdgeDoc(name="test")
        doc.save()
        cas1 = doc._cas

        doc.name = "changed"
        doc.save()
        cas2 = doc._cas

        assert cas1 is not None
        assert cas2 is not None
        assert cas1 != cas2

    def test_save_with_validation_disabled(self):
        doc = EdgeDoc()  # name is required, but we skip validation
        doc.save(validate=False)
        assert doc._is_new is False


@integration_mark
class TestQueryEdgeCases:
    """Test query edge cases against real Couchbase."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_filter_by_missing_field(self):
        EdgeDoc(name="with_age", age=25).save()
        EdgeDoc(name="no_age").save()
        # Documents without age set should not appear when filtering for age values
        results = list(EdgeDoc.objects.filter(age=25))
        names = {r.name for r in results}
        assert "with_age" in names
        assert "no_age" not in names

    def test_filter_chain(self):
        EdgeDoc(name="alice", age=30, active=True).save()
        EdgeDoc(name="bob", age=25, active=True).save()
        EdgeDoc(name="charlie", age=35, active=False).save()

        results = list(EdgeDoc.objects.filter(active=True).filter(age__gte=30))
        assert len(results) == 1
        assert results[0].name == "alice"

    def test_exclude(self):
        EdgeDoc(name="a", age=10).save()
        EdgeDoc(name="b", age=20).save()
        EdgeDoc(name="c", age=30).save()

        results = list(EdgeDoc.objects.exclude(name="b"))
        names = {r.name for r in results}
        assert "b" not in names
        assert len(names) == 2

    def test_order_by_ascending(self):
        EdgeDoc(name="c", age=3).save()
        EdgeDoc(name="a", age=1).save()
        EdgeDoc(name="b", age=2).save()

        results = list(EdgeDoc.objects.order_by("name"))
        names = [r.name for r in results]
        assert names == ["a", "b", "c"]

    def test_order_by_descending(self):
        EdgeDoc(name="a", age=1).save()
        EdgeDoc(name="b", age=2).save()
        EdgeDoc(name="c", age=3).save()

        results = list(EdgeDoc.objects.order_by("-age"))
        ages = [r.age for r in results]
        assert ages == [3, 2, 1]

    def test_limit(self):
        for i in range(10):
            EdgeDoc(name=f"doc_{i}", age=i).save()

        results = list(EdgeDoc.objects.all()[:3])
        assert len(results) == 3

    def test_offset_and_limit(self):
        for i in range(10):
            EdgeDoc(name=f"doc_{i:02d}", age=i).save()

        results = list(EdgeDoc.objects.order_by("name")[2:5])
        assert len(results) == 3

    def test_values_returns_dicts(self):
        EdgeDoc(name="test", age=42).save()
        results = list(EdgeDoc.objects.values("name", "age"))
        assert len(results) == 1
        assert results[0]["name"] == "test"
        assert results[0]["age"] == 42

    def test_values_name_only(self):
        EdgeDoc(name="a", age=1).save()
        EdgeDoc(name="b", age=2).save()

        results = list(EdgeDoc.objects.order_by("name").values("name"))
        names = [r["name"] for r in results]
        assert names == ["a", "b"]

    def test_q_object_or(self):
        from django_couchbase_orm.queryset.q import Q

        EdgeDoc(name="a", age=10).save()
        EdgeDoc(name="b", age=20).save()
        EdgeDoc(name="c", age=30).save()

        results = list(EdgeDoc.objects.filter(Q(name="a") | Q(name="c")))
        names = {r.name for r in results}
        assert names == {"a", "c"}

    def test_q_object_and(self):
        from django_couchbase_orm.queryset.q import Q

        EdgeDoc(name="a", age=10, active=True).save()
        EdgeDoc(name="b", age=10, active=False).save()

        results = list(EdgeDoc.objects.filter(Q(age=10) & Q(active=True)))
        assert len(results) == 1
        assert results[0].name == "a"

    def test_q_object_not(self):
        from django_couchbase_orm.queryset.q import Q

        EdgeDoc(name="a", age=10).save()
        EdgeDoc(name="b", age=20).save()

        results = list(EdgeDoc.objects.filter(~Q(name="a")))
        assert len(results) == 1
        assert results[0].name == "b"

    def test_in_lookup(self):
        EdgeDoc(name="a", age=10).save()
        EdgeDoc(name="b", age=20).save()
        EdgeDoc(name="c", age=30).save()

        results = list(EdgeDoc.objects.filter(name__in=["a", "c"]))
        names = {r.name for r in results}
        assert names == {"a", "c"}

    def test_contains_lookup(self):
        EdgeDoc(name="foobar", age=1).save()
        EdgeDoc(name="barbaz", age=2).save()

        results = list(EdgeDoc.objects.filter(name__contains="bar"))
        assert len(results) == 2

    def test_startswith_lookup(self):
        EdgeDoc(name="foobar", age=1).save()
        EdgeDoc(name="barbaz", age=2).save()

        results = list(EdgeDoc.objects.filter(name__startswith="foo"))
        assert len(results) == 1
        assert results[0].name == "foobar"

    def test_gte_lte_range(self):
        for i in range(10):
            EdgeDoc(name=f"d{i}", age=i * 10).save()

        results = list(EdgeDoc.objects.filter(age__gte=30, age__lte=60))
        ages = sorted(r.age for r in results)
        assert ages == [30, 40, 50, 60]


@integration_mark
class TestCompoundFieldIntegration:
    """Test compound fields (list, dict, embedded) against real Couchbase."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_list_field_roundtrip(self):
        doc = EdgeDoc(name="tagged", tags=["python", "django", "couchbase"])
        doc.save()

        loaded = EdgeDoc.objects.get(pk=doc.pk)
        assert loaded.tags == ["python", "django", "couchbase"]

    def test_empty_list_roundtrip(self):
        doc = EdgeDoc(name="no_tags", tags=[])
        doc.save()

        loaded = EdgeDoc.objects.get(pk=doc.pk)
        assert loaded.tags == []

    def test_dict_field_roundtrip(self):
        doc = EdgeDoc(name="meta", metadata={"version": 2, "env": "prod"})
        doc.save()

        loaded = EdgeDoc.objects.get(pk=doc.pk)
        assert loaded.metadata == {"version": 2, "env": "prod"}

    def test_nested_dict_roundtrip(self):
        doc = EdgeDoc(name="nested", metadata={"a": {"b": {"c": 1}}})
        doc.save()

        loaded = EdgeDoc.objects.get(pk=doc.pk)
        assert loaded.metadata["a"]["b"]["c"] == 1

    def test_boolean_default_persists(self):
        doc = EdgeDoc(name="default_active")
        doc.save()

        loaded = EdgeDoc.objects.get(pk=doc.pk)
        assert loaded.active is True


@integration_mark
class TestDeleteEdgeCases:
    """Test delete operation edge cases."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_delete_nonexistent_raises(self):
        doc = EdgeDoc(_id="nonexistent_id", name="ghost")
        doc._is_new = False
        with pytest.raises(OperationError):
            doc.delete()

    def test_delete_then_exists_false(self):
        doc = EdgeDoc(name="temporary")
        doc.save()
        pk = doc.pk
        doc.delete()
        assert EdgeDoc.objects.filter(pk=pk).exists() is False

    def test_bulk_delete_returns_count(self):
        for i in range(5):
            EdgeDoc(name="bulk_del", age=i).save()

        count = EdgeDoc.objects.filter(name="bulk_del").delete()
        assert count == 5
        assert EdgeDoc.objects.filter(name="bulk_del").count() == 0


@integration_mark
class TestAggregations:
    """Test aggregation operations against real Couchbase."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_count(self):
        for i in range(7):
            EdgeDoc(name=f"count_{i}", age=i).save()

        from django_couchbase_orm.aggregates import Count

        result = EdgeDoc.objects.all().aggregate(total=Count("*"))
        assert result["total"] == 7

    def test_avg(self):
        EdgeDoc(name="a", age=10).save()
        EdgeDoc(name="b", age=20).save()
        EdgeDoc(name="c", age=30).save()

        from django_couchbase_orm.aggregates import Avg

        result = EdgeDoc.objects.all().aggregate(avg_age=Avg("age"))
        assert result["avg_age"] == 20.0

    def test_min_max(self):
        EdgeDoc(name="a", age=5).save()
        EdgeDoc(name="b", age=50).save()
        EdgeDoc(name="c", age=25).save()

        from django_couchbase_orm.aggregates import Max, Min

        result = EdgeDoc.objects.all().aggregate(min_age=Min("age"), max_age=Max("age"))
        assert result["min_age"] == 5
        assert result["max_age"] == 50

    def test_sum(self):
        EdgeDoc(name="a", score=1.5).save()
        EdgeDoc(name="b", score=2.5).save()
        EdgeDoc(name="c", score=3.0).save()

        from django_couchbase_orm.aggregates import Sum

        result = EdgeDoc.objects.all().aggregate(total=Sum("score"))
        assert result["total"] == 7.0

    def test_aggregate_on_empty_set(self):
        from django_couchbase_orm.aggregates import Avg, Count

        result = EdgeDoc.objects.all().aggregate(avg_age=Avg("age"), total=Count("*"))
        assert result["avg_age"] is None
        assert result["total"] == 0


@integration_mark
@pytest.mark.django_db(transaction=True)
class TestDjangoBackendUpdateRegression:
    """Regression tests for Django backend UPDATE operations.

    These specifically test the code path through SQLUpdateCompiler.execute_sql()
    which is where the original bug was (returning cursor instead of int).
    """

    @pytest.fixture(autouse=True)
    def _cleanup(self, settings):
        settings.COUCHBASE = LOCAL_COUCHBASE
        from django_couchbase_orm.connection import reset_connections

        reset_connections()
        _flush_edge_docs()
        yield
        _flush_edge_docs()

    def test_model_save_existing_user(self):
        """user.save() calls _update() internally - must return int > 0."""
        from django.contrib.auth.models import User

        username = f"edge_save_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")

        user.first_name = "Updated"
        user.save()  # This calls _update() which must return int

        reloaded = User.objects.get(pk=user.pk)
        assert reloaded.first_name == "Updated"
        user.delete()

    def test_queryset_update_returns_int(self):
        """QuerySet.update() must return an integer row count."""
        from django.contrib.auth.models import User

        username = f"edge_upd_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        count = User.objects.filter(username=username).update(first_name="Changed")
        assert isinstance(count, int)
        assert count == 1

        User.objects.filter(username=username).first().delete()

    def test_update_comparison_with_zero(self):
        """Django internally does `_update(values) > 0` — must not raise TypeError."""
        from django.contrib.auth.models import User

        username = f"edge_cmp_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@test.com", "pass123")

        # This is the exact pattern Django uses internally

        count = User.objects.filter(pk=user.pk).update(first_name="Test")
        assert count > 0  # Must not raise TypeError

        user.delete()

    def test_login_updates_last_login(self):
        """django.contrib.auth.login() updates last_login field."""
        from django.contrib.auth import authenticate
        from django.contrib.auth.models import User

        username = f"edge_login_{uuid.uuid4().hex[:8]}"
        User.objects.create_user(username, f"{username}@test.com", "pass123")

        user = authenticate(username=username, password="pass123")
        assert user is not None

        # Simulate what login() does: update last_login
        from django.utils import timezone

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])  # Must not raise

        User.objects.filter(username=username).first().delete()
