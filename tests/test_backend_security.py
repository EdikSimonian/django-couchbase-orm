"""Tests for security and performance fixes in the Couchbase backend."""

import pytest

from django_couchbase_orm.db.backends.couchbase.client import DatabaseClient
from django_couchbase_orm.db.backends.couchbase.cursor import (
    CouchbaseCursor,
    _deduplicate_select_columns,
    _fix_aggregate_without_group_by,
    _fix_cast,
    _find_top_level_from,
    _parse_select_columns,
)
from django_couchbase_orm.db.backends.couchbase.operations import DatabaseOperations


class TestC1PasswordNotInArgs:
    """C1: Password must not be in command-line args."""

    def test_password_not_in_args(self):
        args, env = DatabaseClient.settings_to_cmd_args_env(
            {"HOST": "couchbase://localhost", "USER": "admin", "PASSWORD": "secret123"},
            [],
        )
        # Password must NOT appear in args
        assert "secret123" not in args
        assert "-p" not in args
        # Password should be in env
        assert env.get("CB_PASSWORD") == "secret123"

    def test_no_password(self):
        args, env = DatabaseClient.settings_to_cmd_args_env(
            {"HOST": "couchbase://localhost", "USER": "admin"},
            [],
        )
        assert env is None
        assert "-p" not in args


class TestC2GetNextIdFailure:
    """C2: get_next_id must not silently return 1 on failure."""

    def test_raises_on_failure(self):
        """If the counter fails, it must raise, not return 1."""
        from unittest.mock import MagicMock

        fake_cluster = MagicMock()
        fake_bucket = MagicMock()
        fake_cluster.bucket.return_value = fake_bucket
        fake_collection = MagicMock()
        fake_bucket.scope.return_value.collection.return_value = fake_collection
        # Make increment fail
        fake_collection.binary.return_value.increment.side_effect = Exception("Connection failed")

        from django_couchbase_orm.db.backends.couchbase.fields import get_next_id

        with pytest.raises(Exception):
            get_next_id(fake_cluster, "bucket", "scope", "table")


class TestH3BacktickEscaping:
    """H3: quote_name must escape embedded backticks."""

    def test_simple_name(self):
        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.quote_name("table") == "`table`"

    def test_already_quoted(self):
        ops = DatabaseOperations.__new__(DatabaseOperations)
        assert ops.quote_name("`table`") == "`table`"

    def test_embedded_backtick(self):
        ops = DatabaseOperations.__new__(DatabaseOperations)
        result = ops.quote_name("bad`name")
        # Embedded backtick should be escaped
        assert result == "`bad``name`"

    def test_injection_attempt(self):
        ops = DatabaseOperations.__new__(DatabaseOperations)
        malicious = "x` UNION SELECT 1 --"
        result = ops.quote_name(malicious)
        # The backtick should be doubled, preventing injection
        assert "``" in result
        assert result.startswith("`")
        assert result.endswith("`")


class TestP1ScanConsistency:
    """P1: Scan consistency should be configurable, not hardcoded."""

    def test_scan_consistency_configurable(self):
        """Verify cursor accepts scan_consistency parameter."""
        import inspect

        sig = inspect.signature(CouchbaseCursor.__init__)
        assert "scan_consistency" in sig.parameters

    def test_default_is_request_plus(self):
        """Default should be request_plus for Django's read-after-write safety."""
        import inspect

        sig = inspect.signature(CouchbaseCursor.__init__)
        default = sig.parameters["scan_consistency"].default
        assert default == "request_plus"

    def test_uses_instance_consistency(self):
        """Cursor should use self._scan_consistency, not hardcoded."""
        import inspect

        source = inspect.getsource(CouchbaseCursor.execute)
        assert "self._scan_consistency" in source


class TestM1ErrorHandlerSelectOnly:
    """M1: Error 3000/4210 handler should only catch SELECT queries."""

    def test_handler_checks_select(self):
        """Verify the error handler restricts to SELECT."""
        import inspect

        source = inspect.getsource(CouchbaseCursor.execute)
        # Should check for SELECT specifically
        assert 'startswith("SELECT")' in source or "startswith('SELECT')" in source


class TestP6NoDuplicateDedup:
    """P6: Only one _deduplicate_select_columns should exist."""

    def test_single_definition(self):
        """Verify there's only one definition of _deduplicate_select_columns."""
        import inspect

        source = inspect.getsource(
            __import__(
                "django_couchbase_orm.db.backends.couchbase.cursor",
                fromlist=["cursor"],
            )
        )
        count = source.count("def _deduplicate_select_columns")
        assert count == 1, f"Found {count} definitions, expected 1"


class TestL1NoWeakPasswordDefault:
    """L1: No weak password default."""

    def test_empty_password_default(self):
        """Password should default to empty string, not 'password'."""
        import inspect
        from django_couchbase_orm.db.backends.couchbase.base import DatabaseWrapper

        source = inspect.getsource(DatabaseWrapper.get_connection_params)
        assert '"password"' not in source or 'PASSWORD", ""' in source


class TestColumnParsingWithSubqueries:
    """Test that column parsing handles EXISTS subqueries correctly."""

    def test_exists_subquery_columns(self):
        sql = (
            "SELECT `t`.`id` AS `pk`, `t`.`ct_id` AS `content_type`, "
            "EXISTS(SELECT %s AS `a` FROM `x`.`y`.`z` U0 LIMIT 1) AS `_is_site_root`, "
            "EXISTS(SELECT %s AS `a` FROM `x`.`y`.`w` U0 LIMIT 1) AS `_approved` "
            "FROM `x`.`y`.`t`"
        )
        cols = _parse_select_columns(sql)
        assert cols == ["pk", "content_type", "_is_site_root", "_approved"]

    def test_find_top_level_from_skips_subquery(self):
        sql = "EXISTS(SELECT 1 FROM inner_table) AS col1 FROM outer_table"
        pos = _find_top_level_from(sql)
        assert sql[pos : pos + 4] == "FROM"
        assert "outer_table" in sql[pos:]


class TestInClauseCollapse:
    """Test IN clause collapse handles edge cases correctly."""

    def test_in_with_outer_parens_preserved(self):
        sql = "DELETE FROM t WHERE (user_id = %s AND group_id IN (%s))"
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, [1, 2])
        assert new_sql.count("(") == new_sql.count(")"), "Unbalanced parens!"
        assert new_params == [1, [2]]

    def test_in_with_double_wrapped_parens(self):
        sql = "SELECT * FROM t WHERE id IN ((%s), (%s))"
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, [1, 2])
        assert new_params == [[1, 2]]

    def test_no_in_clause(self):
        sql = "SELECT * FROM t WHERE x = %s"
        new_sql, new_params = CouchbaseCursor._collapse_in_clauses(sql, ["a"])
        assert new_sql == sql
        assert new_params == ["a"]


class TestDeduplicateColumns:
    """Test column deduplication with subqueries."""

    def test_dedup_with_exists(self):
        sql = (
            "SELECT `t1`.`id`, `t1`.`status`, "
            "(SELECT `U0`.`id` AS `pk` FROM `x`.`y`.`rev` U0 LIMIT 1) AS `prev`, "
            "`t2`.`id`, `t3`.`id` "
            "FROM `x`.`y`.`t1`"
        )
        result = _deduplicate_select_columns(sql)
        assert "id__2" in result
        assert "id__3" in result

    def test_no_dedup_needed(self):
        sql = "SELECT `a`, `b`, `c` FROM `table`"
        result = _deduplicate_select_columns(sql)
        assert result == sql


class TestCastFix:
    """Test CAST to N1QL function conversion."""

    def test_cast_integer(self):
        result = _fix_cast("CAST(x AS integer)")
        assert result == "TONUMBER(x)"

    def test_cast_varchar(self):
        result = _fix_cast("CAST(x AS varchar)")
        assert result == "TOSTRING(x)"

    def test_cast_boolean(self):
        result = _fix_cast("CAST(x AS boolean)")
        assert result == "TOBOOLEAN(x)"

    def test_no_cast(self):
        sql = "SELECT x FROM t"
        assert _fix_cast(sql) == sql


class TestAggregateWithoutGroupBy:
    """Test aggregate-without-GROUP-BY fix."""

    def test_strips_non_aggregate_columns(self):
        sql = "SELECT `id`, `name`, COUNT(*) AS `__count` FROM `table`"
        result = _fix_aggregate_without_group_by(sql)
        assert "id" not in result
        assert "name" not in result
        assert "COUNT(*)" in result

    def test_preserves_with_group_by(self):
        sql = "SELECT `id`, COUNT(*) AS `cnt` FROM `table` GROUP BY `id`"
        result = _fix_aggregate_without_group_by(sql)
        assert result == sql

    def test_preserves_no_aggregate(self):
        sql = "SELECT `id`, `name` FROM `table`"
        result = _fix_aggregate_without_group_by(sql)
        assert result == sql
