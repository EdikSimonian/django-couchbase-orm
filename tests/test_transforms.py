"""Tests for lookup transforms."""

import pytest

from django_couchbase_orm.query.n1ql import N1QLQuery
from django_couchbase_orm.queryset.transform import apply_lookup, parse_lookup


class TestParseLookup:
    def test_no_lookup(self):
        assert parse_lookup("name") == ("name", "exact")

    def test_exact(self):
        assert parse_lookup("name__exact") == ("name", "exact")

    def test_gt(self):
        assert parse_lookup("age__gt") == ("age", "gt")

    def test_gte(self):
        assert parse_lookup("age__gte") == ("age", "gte")

    def test_lt(self):
        assert parse_lookup("age__lt") == ("age", "lt")

    def test_lte(self):
        assert parse_lookup("age__lte") == ("age", "lte")

    def test_in(self):
        assert parse_lookup("status__in") == ("status", "in")

    def test_contains(self):
        assert parse_lookup("name__contains") == ("name", "contains")

    def test_icontains(self):
        assert parse_lookup("name__icontains") == ("name", "icontains")

    def test_startswith(self):
        assert parse_lookup("name__startswith") == ("name", "startswith")

    def test_endswith(self):
        assert parse_lookup("name__endswith") == ("name", "endswith")

    def test_isnull(self):
        assert parse_lookup("email__isnull") == ("email", "isnull")

    def test_regex(self):
        assert parse_lookup("name__regex") == ("name", "regex")

    def test_between(self):
        assert parse_lookup("age__between") == ("age", "between")

    def test_iexact(self):
        assert parse_lookup("name__iexact") == ("name", "iexact")

    def test_unknown_treated_as_field_path(self):
        """Unknown suffixes are treated as part of the field name (nested path)."""
        assert parse_lookup("address__city") == ("address__city", "exact")

    def test_nested_with_lookup(self):
        assert parse_lookup("address__city__contains") == ("address__city", "contains")


class TestApplyLookup:
    def _make_query(self):
        return N1QLQuery("b", "s", "c")

    def test_exact(self):
        q = self._make_query()
        clause = apply_lookup(q, "name", "Alice")
        assert clause == "d.`name` = $1"
        _, params = q.build()
        assert "Alice" in params

    def test_exact_none(self):
        q = self._make_query()
        clause = apply_lookup(q, "name", None)
        assert clause == "d.`name` IS NULL"

    def test_ne(self):
        q = self._make_query()
        clause = apply_lookup(q, "status__ne", "deleted")
        assert clause == "d.`status` != $1"

    def test_ne_none(self):
        q = self._make_query()
        clause = apply_lookup(q, "status__ne", None)
        assert clause == "d.`status` IS NOT NULL"

    def test_gt(self):
        q = self._make_query()
        clause = apply_lookup(q, "age__gt", 18)
        assert clause == "d.`age` > $1"

    def test_gte(self):
        q = self._make_query()
        clause = apply_lookup(q, "age__gte", 18)
        assert clause == "d.`age` >= $1"

    def test_lt(self):
        q = self._make_query()
        clause = apply_lookup(q, "age__lt", 65)
        assert clause == "d.`age` < $1"

    def test_lte(self):
        q = self._make_query()
        clause = apply_lookup(q, "age__lte", 65)
        assert clause == "d.`age` <= $1"

    def test_in(self):
        q = self._make_query()
        clause = apply_lookup(q, "status__in", ["active", "pending"])
        assert clause == "d.`status` IN $1"

    def test_in_requires_iterable(self):
        q = self._make_query()
        with pytest.raises(ValueError, match="list/tuple/set"):
            apply_lookup(q, "status__in", "active")

    def test_contains(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__contains", "brew")
        assert clause == "CONTAINS(d.`name`, $1)"

    def test_icontains(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__icontains", "BREW")
        assert clause == "CONTAINS(LOWER(d.`name`), $1)"
        # Value should be lowered
        assert q._params[-1] == "brew"

    def test_startswith(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__startswith", "21st")
        assert clause == "d.`name` LIKE $1"
        assert q._params[-1] == "21st%"

    def test_istartswith(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__istartswith", "21ST")
        assert clause == "LOWER(d.`name`) LIKE $1"
        assert q._params[-1] == "21st%"

    def test_endswith(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__endswith", "IPA")
        assert clause == "d.`name` LIKE $1"
        assert q._params[-1] == "%IPA"

    def test_iendswith(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__iendswith", "IPA")
        assert clause == "LOWER(d.`name`) LIKE $1"
        assert q._params[-1] == "%ipa"

    def test_isnull_true(self):
        q = self._make_query()
        clause = apply_lookup(q, "email__isnull", True)
        assert clause == "d.`email` IS NULL"

    def test_isnull_false(self):
        q = self._make_query()
        clause = apply_lookup(q, "email__isnull", False)
        assert clause == "d.`email` IS NOT NULL"

    def test_regex(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__regex", "^[A-Z].*")
        assert clause == "REGEXP_CONTAINS(d.`name`, $1)"

    def test_iregex(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__iregex", "^brew.*")
        assert clause == "REGEXP_CONTAINS(d.`name`, $1)"
        assert q._params[-1] == "(?i)^brew.*"

    def test_between(self):
        q = self._make_query()
        clause = apply_lookup(q, "age__between", [18, 65])
        assert clause == "d.`age` BETWEEN $1 AND $2"

    def test_between_requires_two_values(self):
        q = self._make_query()
        with pytest.raises(ValueError, match="exactly 2"):
            apply_lookup(q, "age__between", [18])

    def test_iexact(self):
        q = self._make_query()
        clause = apply_lookup(q, "name__iexact", "ALICE")
        assert clause == "LOWER(d.`name`) = $1"
        assert q._params[-1] == "alice"

    def test_unknown_suffix_treated_as_field_path(self):
        """Unknown suffixes are treated as nested field paths with exact lookup."""
        q = self._make_query()
        # 'nonexistent_lookup' is not a registered lookup, so parse_lookup
        # treats 'name__nonexistent_lookup' as a nested JSON path.
        clause = apply_lookup(q, "name__nonexistent_lookup", "x")
        assert clause == "d.`name`.`nonexistent_lookup` = $1"

    def test_nested_path_exact(self):
        q = self._make_query()
        clause = apply_lookup(q, "address__city", "Brooklyn")
        assert clause == "d.`address`.`city` = $1"

    def test_nested_path_with_lookup(self):
        q = self._make_query()
        clause = apply_lookup(q, "address__city__contains", "rook")
        assert clause == "CONTAINS(d.`address`.`city`, $1)"

    def test_nested_path_three_levels(self):
        q = self._make_query()
        clause = apply_lookup(q, "address__zip__primary", "11201")
        assert clause == "d.`address`.`zip`.`primary` = $1"

    def test_nested_path_rejects_injection(self):
        q = self._make_query()
        with pytest.raises(ValueError, match="Invalid identifier"):
            apply_lookup(q, "address__city`); DROP COLLECTION x;--", "x")

    def test_params_accumulate(self):
        """Multiple lookups should accumulate params correctly."""
        q = self._make_query()
        apply_lookup(q, "name", "Alice")
        apply_lookup(q, "age__gte", 18)
        apply_lookup(q, "status__in", ["active", "pending"])
        assert q._params == ["Alice", 18, ["active", "pending"]]
