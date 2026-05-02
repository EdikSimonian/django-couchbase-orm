"""DB-API 2.0 compatible cursor for Couchbase N1QL queries.

The free functions in the lower half of this module (``_fix_*``,
``_deduplicate_select_columns``, ``_collapse_in_clauses`` etc.) are regex-
based SQL rewriters applied to whatever Django's compilers emit. They are
brittle around quoted identifiers, nested subqueries, and string literals
that resemble SQL keywords — treat them as last-resort compatibility shims,
not a parser. New translations should land as Django compiler hooks
(``Func.as_couchbase``, ``Operations`` overrides, custom compilers) and
this layer should keep shrinking.
"""

from __future__ import annotations

import re

from couchbase.options import QueryOptions

# Pattern to extract column names/aliases from a SELECT clause.
_SELECT_COLUMNS_RE = re.compile(
    r"SELECT\s+(?:DISTINCT\s+)?(.*?)\s+FROM\s+",
    re.IGNORECASE | re.DOTALL,
)


def _find_top_level_from(sql: str) -> int:
    """Find the position of the top-level FROM keyword (not inside subqueries)."""
    depth = 0
    upper = sql.upper()
    for i in range(len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
        elif depth == 0 and upper[i : i + 5] == "FROM ":
            return i
    return -1


def _parse_select_columns(sql: str) -> list[str] | None:
    """Extract the expected column order from a SELECT statement.

    Returns a list of column names/aliases in SELECT order, or None if
    the SELECT clause cannot be parsed (e.g., SELECT *).
    Uses paren-aware parsing to skip over subqueries like EXISTS(SELECT ... FROM ...).
    """
    sql_stripped = sql.strip()
    prefix_match = re.match(r"SELECT\s+(?:DISTINCT\s+)?", sql_stripped, re.IGNORECASE)
    if not prefix_match:
        return None

    after_select = sql_stripped[prefix_match.end() :]
    from_pos = _find_top_level_from(after_select)
    if from_pos == -1:
        return None

    select_part = after_select[:from_pos].strip()
    if select_part == "*" or select_part.endswith(".*"):
        return None

    columns = []
    depth = 0
    current = []
    for ch in select_part:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            columns.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        columns.append("".join(current).strip())

    # Extract the alias or column name from each expression.
    result = []
    for col_expr in columns:
        # Handle "expr AS alias" or "expr alias"
        as_match = re.search(r'\bAS\s+[`"]?(\w+)[`"]?\s*$', col_expr, re.IGNORECASE)
        if as_match:
            result.append(as_match.group(1))
            continue

        # Handle backtick-quoted: `table`.`col` -> col
        backtick_match = re.search(r"`(\w+)`\s*$", col_expr)
        if backtick_match:
            result.append(backtick_match.group(1))
            continue

        # Handle dotted: d.col_name -> col_name
        dot_match = re.search(r"\.(\w+)\s*$", col_expr)
        if dot_match:
            result.append(dot_match.group(1))
            continue

        # Plain column name.
        plain = col_expr.strip().strip("`").strip('"')
        if plain:
            result.append(plain)

    return result if result else None


def _fix_positional_order_by(sql: str, columns: list[str] | None) -> str:
    """Replace positional ORDER BY references (ORDER BY 1, 2) with column names.

    N1QL does not support positional column references in ORDER BY.
    """
    if "ORDER BY" not in sql.upper():
        return sql

    if columns is None:
        return sql

    def replace_positional(match):
        pos = int(match.group(1))
        suffix = match.group(2)  # ASC or DESC
        if 1 <= pos <= len(columns):
            col = columns[pos - 1]
            return f"`{col}` {suffix}" if suffix else f"`{col}`"
        return match.group(0)

    # Match positional refs like "1 ASC", "2 DESC", or bare "1"
    order_pattern = re.compile(
        r"(?<=ORDER BY\s)(.+?)$",
        re.IGNORECASE | re.DOTALL,
    )
    m = order_pattern.search(sql)
    if not m:
        return sql

    order_clause = m.group(1)
    # Check for LIMIT/OFFSET at the end
    limit_match = re.search(r"\s+(LIMIT\s+.*)$", order_clause, re.IGNORECASE)
    limit_part = ""
    if limit_match:
        limit_part = " " + limit_match.group(1)
        order_clause = order_clause[: limit_match.start()]

    parts = order_clause.split(",")
    new_parts = []
    for part in parts:
        part = part.strip()
        pos_match = re.match(r"^(\d+)\s*(ASC|DESC)?\s*$", part, re.IGNORECASE)
        if pos_match:
            pos = int(pos_match.group(1))
            suffix = pos_match.group(2) or ""
            if 1 <= pos <= len(columns):
                col = columns[pos - 1]
                new_parts.append(f"`{col}` {suffix}".strip())
            else:
                new_parts.append(part)
        else:
            new_parts.append(part)

    new_order = ", ".join(new_parts)
    return sql[: m.start(1)] + new_order + limit_part


def _parse_select_expressions(sql: str) -> list[str] | None:
    """Extract the full SELECT expressions (before AS alias) in order.

    Used for GROUP BY fix — N1QL requires GROUP BY to use the original
    expression, not the alias.
    """
    m = _SELECT_COLUMNS_RE.match(sql.strip())
    if not m:
        return None
    select_part = m.group(1).strip()
    if select_part == "*" or select_part.endswith(".*"):
        return None

    expressions = []
    depth = 0
    current = []
    for ch in select_part:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            expressions.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        expressions.append("".join(current).strip())

    # Strip the AS alias from each expression to get the raw expression.
    result = []
    for expr in expressions:
        as_match = re.search(r"\s+AS\s+[`\"]?\w+[`\"]?\s*$", expr, re.IGNORECASE)
        if as_match:
            result.append(expr[: as_match.start()].strip())
        else:
            result.append(expr)
    return result if result else None


def _fix_positional_group_by(sql: str, columns: list[str] | None) -> str:
    """Replace positional GROUP BY references (GROUP BY 1, 2) with full expressions.

    N1QL does not support positional references OR alias references in GROUP BY.
    We must use the original SELECT expressions.
    """
    # Parse the original SELECT expressions (not aliases).
    select_exprs = _parse_select_expressions(sql)
    if select_exprs is None:
        return sql

    group_pattern = re.compile(
        r"GROUP BY\s+(.+?)(?=\s+HAVING|\s+ORDER|\s+LIMIT|\s+OFFSET|\s*$)",
        re.IGNORECASE,
    )
    m = group_pattern.search(sql)
    if not m:
        return sql

    group_clause = m.group(1)
    parts = group_clause.split(",")
    new_parts = []
    for part in parts:
        part = part.strip()
        pos_match = re.match(r"^(\d+)\s*$", part)
        if pos_match:
            pos = int(pos_match.group(1))
            if 1 <= pos <= len(select_exprs):
                new_parts.append(select_exprs[pos - 1])
            else:
                new_parts.append(part)
        else:
            new_parts.append(part)

    new_group = ", ".join(new_parts)
    return sql[: m.start(1)] + new_group + sql[m.end(1) :]


def _fix_aggregate_without_group_by(sql: str) -> str:
    """Fix SELECT that mixes regular columns with aggregates without GROUP BY.

    N1QL (unlike some SQL databases) requires GROUP BY when mixing regular
    columns with aggregate functions. When Django generates:
        SELECT col1, col2, COUNT(*) AS __count FROM keyspace
    we convert it to:
        SELECT COUNT(*) AS __count FROM keyspace

    This pattern occurs in Django's QuerySet.count() on distinct querysets.
    """
    sql_upper = sql.strip().upper()
    if "GROUP BY" in sql_upper or "COUNT(" not in sql_upper:
        return sql

    # Check if there's a mix of aggregate and non-aggregate columns.
    m = re.match(
        r"(SELECT\s+(?:DISTINCT\s+)?)(.*?)(\s+FROM\s+.*)",
        sql.strip(),
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return sql

    select_part = m.group(2)

    # Parse columns.
    columns = []
    depth = 0
    current = []
    for ch in select_part:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            columns.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        columns.append("".join(current).strip())

    if len(columns) <= 1:
        return sql

    # Classify columns as aggregate or regular.
    agg_pattern = re.compile(
        r"^\s*(COUNT|SUM|AVG|MIN|MAX|ARRAY_AGG)\s*\(",
        re.IGNORECASE,
    )
    agg_cols = []
    regular_cols = []
    for col in columns:
        if agg_pattern.match(col):
            agg_cols.append(col)
        else:
            regular_cols.append(col)

    if not agg_cols or not regular_cols:
        return sql

    # Has both regular and aggregate columns without GROUP BY.
    # Keep only the aggregate columns.
    new_select = ", ".join(agg_cols)
    return m.group(1).rstrip() + " " + new_select + m.group(3)


def _deduplicate_select_columns(sql: str) -> str:
    """Add unique aliases to duplicate column names in a SELECT statement.

    N1QL doesn't allow two result columns with the same name.
    Uses _find_top_level_from for subquery-aware parsing.
    """
    sql_stripped = sql.strip()
    prefix_match = re.match(r"(SELECT\s+(?:DISTINCT\s+)?)", sql_stripped, re.IGNORECASE)
    if not prefix_match:
        return sql

    prefix = prefix_match.group(1)
    after_select = sql_stripped[prefix_match.end() :]
    from_pos = _find_top_level_from(after_select)
    if from_pos == -1:
        return sql

    select_part = after_select[:from_pos].strip()
    from_and_rest = after_select[from_pos:]

    # Split columns respecting parentheses.
    columns = []
    depth = 0
    current = []
    for ch in select_part:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            columns.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        columns.append("".join(current).strip())

    if len(columns) <= 1:
        return sql

    def get_result_name(col_expr):
        as_match = re.search(r"\bAS\s+`?(\w+)`?\s*$", col_expr, re.IGNORECASE)
        if as_match:
            return as_match.group(1)
        if col_expr.strip().startswith("("):
            return None
        backtick = re.search(r"`(\w+)`\s*$", col_expr)
        if backtick:
            return backtick.group(1)
        dot = re.search(r"\.(\w+)\s*$", col_expr)
        if dot:
            return dot.group(1)
        return col_expr.strip()

    names = [get_result_name(c) for c in columns]
    seen = {}
    has_dups = False
    for name in names:
        if name is None:
            continue
        if name in seen:
            has_dups = True
            break
        seen[name] = True

    if not has_dups:
        return sql

    seen = {}
    new_columns = []
    for col_expr, name in zip(columns, names):
        if name is not None and name in seen:
            seen[name] += 1
            alias = f"{name}__{seen[name]}"
            if re.search(r"\bAS\s+`?\w+`?\s*$", col_expr, re.IGNORECASE):
                col_expr = re.sub(r"\bAS\s+`?\w+`?\s*$", f"AS `{alias}`", col_expr, flags=re.IGNORECASE)
            else:
                col_expr = f"{col_expr} AS `{alias}`"
        else:
            if name is not None:
                seen[name] = 1
        new_columns.append(col_expr)

    return prefix + ", ".join(new_columns) + " " + from_and_rest


def _fix_cast(sql: str) -> str:
    """Replace SQL CAST(expr AS type) with N1QL type conversion functions.

    N1QL doesn't support CAST syntax. It uses TONUMBER(), TOSTRING(), etc.
    """
    cast_map = {
        "integer": "TONUMBER",
        "int": "TONUMBER",
        "bigint": "TONUMBER",
        "smallint": "TONUMBER",
        "float": "TONUMBER",
        "real": "TONUMBER",
        "double": "TONUMBER",
        "numeric": "TONUMBER",
        "decimal": "TONUMBER",
        "number": "TONUMBER",
        "text": "TOSTRING",
        "varchar": "TOSTRING",
        "char": "TOSTRING",
        "boolean": "TOBOOLEAN",
        "bool": "TOBOOLEAN",
    }

    def replace_cast(match):
        expr = match.group(1).strip()
        type_name = match.group(2).strip().lower()
        # Strip length specifiers like varchar(255)
        base_type = type_name.split("(")[0].strip()
        func = cast_map.get(base_type, "TOSTRING")
        return f"{func}({expr})"

    return re.sub(
        r"\bCAST\s*\(\s*(.*?)\s+AS\s+(\w+(?:\([^)]*\))?)\s*\)",
        replace_cast,
        sql,
        flags=re.IGNORECASE,
    )


def _fix_in_subquery(sql: str) -> str:
    """Add RAW keyword to subqueries inside IN clauses.

    N1QL's IN operator expects scalar values, but Django generates
    `IN (SELECT col AS alias FROM ...)` which returns objects.
    We need `IN (SELECT RAW col FROM ...)` to return scalars.

    Only modifies single-column subqueries inside IN(...).
    """
    # Find IN (SELECT ... FROM ...) patterns.
    # We need to handle nested parens carefully.
    result = []
    i = 0
    sql_upper = sql.upper()
    while i < len(sql):
        # Look for "IN ("
        in_pos = sql_upper.find("IN (SELECT ", i)
        if in_pos == -1:
            in_pos = sql_upper.find("IN(SELECT ", i)
        if in_pos == -1:
            result.append(sql[i:])
            break

        # Check it's actually "IN" (not part of "INNER JOIN" etc.)
        # Look for word boundary before IN
        if in_pos > 0 and sql[in_pos - 1].isalpha():
            result.append(sql[i : in_pos + 2])
            i = in_pos + 2
            continue

        # Find the opening paren after IN
        paren_start = sql.index("(", in_pos + 2)
        result.append(sql[i : paren_start + 1])
        i = paren_start + 1

        # Find the matching closing paren
        depth = 1
        j = i
        while j < len(sql) and depth > 0:
            if sql[j] == "(":
                depth += 1
            elif sql[j] == ")":
                depth -= 1
            j += 1
        subquery = sql[i : j - 1]  # Content inside the parens

        # Check if it's a SELECT with a single column and has AS alias.
        # Replace "SELECT expr AS alias" with "SELECT RAW expr"
        sub_stripped = subquery.strip()
        if sub_stripped.upper().startswith("SELECT "):
            # Find FROM in the subquery (at the top level only)
            from_match = re.search(r"\bFROM\b", sub_stripped, re.IGNORECASE)
            if from_match:
                select_part = sub_stripped[7 : from_match.start()].strip()
                rest = sub_stripped[from_match.start() :]
                # Check if it's a single column (no commas at top level)
                comma_depth = 0
                has_top_comma = False
                for ch in select_part:
                    if ch == "(":
                        comma_depth += 1
                    elif ch == ")":
                        comma_depth -= 1
                    elif ch == "," and comma_depth == 0:
                        has_top_comma = True
                        break
                if not has_top_comma:
                    # Single column — strip AS alias and add RAW
                    as_match = re.search(
                        r"\s+AS\s+[`\"]?\w+[`\"]?\s*$",
                        select_part,
                        re.IGNORECASE,
                    )
                    if as_match:
                        select_part = select_part[: as_match.start()].strip()
                    # Check if DISTINCT is present — N1QL syntax is
                    # SELECT DISTINCT RAW expr, not SELECT RAW DISTINCT.
                    if select_part.upper().startswith("DISTINCT "):
                        expr = select_part[9:].strip()
                        result.append(f"SELECT DISTINCT RAW {expr} {rest}")
                    else:
                        result.append(f"SELECT RAW {select_part} {rest}")
                    result.append(")")
                    i = j
                    continue

        # No modification needed — keep the subquery as-is
        result.append(subquery)
        result.append(")")
        i = j

    return "".join(result)


class CouchbaseCursor:
    """Wraps Couchbase SDK query execution with a DB-API 2.0 interface.

    Translates Django's %s-style parameters to N1QL's $1, $2, ... positional
    parameters and executes queries via cluster.query().
    """

    def __init__(
        self,
        cluster,
        bucket_name,
        scope_name="_default",
        scan_consistency="request_plus",
        adhoc=True,
        wrapper=None,
        graceful_query_errors=False,
    ):
        self._cluster = cluster
        self._bucket_name = bucket_name
        self._scope_name = scope_name
        self._scan_consistency = scan_consistency
        self._adhoc = adhoc  # False = use prepared statement caching.
        self._wrapper = wrapper  # DatabaseWrapper ref for transaction state.
        # When True, certain N1QL syntax / unsupported-pattern errors on SELECT
        # are downgraded to "no rows" instead of raising. Default is False:
        # query errors propagate so callers see broken queries immediately.
        self._graceful_query_errors = graceful_query_errors
        self._results = None
        self._rows: list[tuple] = []
        self._row_index = 0
        self._description = None
        self._rowcount = -1
        self._lastrowid = None
        self._closed = False

    @property
    def description(self):
        return self._description

    @property
    def rowcount(self):
        return self._rowcount

    @property
    def lastrowid(self):
        return self._lastrowid

    def _convert_params(self, sql: str, params: tuple | list | None) -> tuple[str, list]:
        """Convert Django's %s placeholders to N1QL $1, $2, ... positional params.

        Also handles the IN clause: Django generates `IN (%s, %s, %s)` with
        separate params, but N1QL needs `IN $N` with an array parameter.
        """
        if params is None:
            return sql, []

        params_list = list(params)

        # First, collapse IN (%s, %s, ...) into a single array parameter.
        sql, params_list = self._collapse_in_clauses(sql, params_list)

        counter = [0]

        def replace_placeholder(match):
            counter[0] += 1
            return f"${counter[0]}"

        # Replace %s with $N, but not %%s (escaped percent).
        converted = re.sub(r"(?<!%)%s", replace_placeholder, sql)
        # Unescape %% to %.
        converted = converted.replace("%%", "%")
        return converted, params_list

    @staticmethod
    def _collapse_in_clauses(sql: str, params: list) -> tuple[str, list]:
        """Collapse `IN (%s, %s, ...)` into `IN %s` with an array parameter.

        N1QL's IN operator expects a single array value, not a comma-separated list.
        """
        # Find IN (%s, %s, ...) patterns.
        # Match IN followed by ( then %s placeholders separated by commas then ).
        # Each %s may optionally be wrapped in parens: (%s).
        # We use a simple approach: find "IN (" then count parens to find the matching ")".
        in_pattern = re.compile(r"\bIN\s*\(", re.IGNORECASE)

        # Find all IN ( positions, then manually find the matching close paren
        matches = []
        for m in in_pattern.finditer(sql):
            start = m.start()
            m.end() - 1  # position of the opening (
            # Find matching )
            depth = 1
            i = m.end()
            while i < len(sql) and depth > 0:
                if sql[i] == "(":
                    depth += 1
                elif sql[i] == ")":
                    depth -= 1
                i += 1
            if depth == 0:
                inner = sql[m.end() : i - 1]  # content inside the parens
                # Check if it contains only %s placeholders (possibly wrapped in parens)
                stripped = inner.replace("(", "").replace(")", "")
                placeholders = [p.strip() for p in stripped.split(",")]
                if all(p == "%s" for p in placeholders if p):
                    matches.append((start, i, inner, len(placeholders)))

        if not matches:
            return sql, params

        new_params = []
        param_index = 0
        last_end = 0
        result_parts = []

        for start, end, inner, placeholder_count in matches:
            # Add everything before this match, consuming params along the way.
            before = sql[last_end:start]
            before_count = before.count("%s")
            for _ in range(before_count):
                new_params.append(params[param_index])
                param_index += 1
            result_parts.append(before)

            # Collect the IN values into an array.
            array_values = params[param_index : param_index + placeholder_count]
            param_index += placeholder_count
            new_params.append(list(array_values))
            result_parts.append("IN %s")

            last_end = end

        # Add the remainder.
        remainder = sql[last_end:]
        remainder_count = remainder.count("%s")
        for _ in range(remainder_count):
            new_params.append(params[param_index])
            param_index += 1
        result_parts.append(remainder)

        return "".join(result_parts), new_params

    @staticmethod
    def _normalize_value(v):
        """Normalize N1QL result values for Django compatibility.

        - Empty list [] → None (N1QL returns [] for missing/null subquery results)
        - Single-element list [{'col': val}] → val (N1QL scalar subquery result)
        - Single-element list [val] → val (N1QL RAW subquery result)
        """
        if isinstance(v, list):
            if len(v) == 0:
                return None
            if len(v) == 1:
                item = v[0]
                if isinstance(item, dict) and len(item) == 1:
                    return next(iter(item.values()))
                return item
        return v

    def _get_scope(self):
        bucket = self._cluster.bucket(self._bucket_name)
        return bucket.scope(self._scope_name)

    def execute(self, sql: str, params: tuple | list | None = None):
        """Execute a N1QL query."""
        if self._closed:
            raise Exception("Cursor is closed.")

        self._rows = []
        self._row_index = 0
        self._description = None
        self._rowcount = -1
        self._lastrowid = None

        sql_stripped = sql.strip()

        # Handle no-op or empty queries.
        if not sql_stripped:
            return

        # Parse column order for positional ORDER BY / GROUP BY fixes.
        # This must happen before those fixes modify the SQL.
        pre_fix_columns = _parse_select_columns(sql_stripped)

        # Fix positional ORDER BY and GROUP BY — N1QL doesn't support
        # positional references like ORDER BY 1 or GROUP BY 1, 2, 3.
        sql_stripped = _fix_positional_order_by(sql_stripped, pre_fix_columns)
        sql_stripped = _fix_positional_group_by(sql_stripped, pre_fix_columns)

        # Fix IN (SELECT ...) subqueries — N1QL needs SELECT RAW for scalars.
        sql_stripped = _fix_in_subquery(sql_stripped)

        # Fix aggregation without GROUP BY — N1QL is stricter than SQL.
        sql_stripped = _fix_aggregate_without_group_by(sql_stripped)

        # Fix bare table names (without keyspace) in DML statements.
        sql_stripped = self._fix_bare_table_names(sql_stripped)

        # Fix CAST(x AS type) — N1QL uses TOSTRING/TONUMBER/TOBOOLEAN instead.
        sql_stripped = _fix_cast(sql_stripped)

        # Fix IS NULL / IS NOT NULL — N1QL distinguishes between NULL and
        # MISSING (field doesn't exist in document). Django expects IS NULL
        # to match both. We use IS VALUED / IS NOT VALUED which covers both.
        sql_stripped = re.sub(
            r"(`[^`]+`(?:\.`[^`]+`)*)\s+IS\s+NOT\s+NULL\b",
            r"\1 IS VALUED",
            sql_stripped,
            flags=re.IGNORECASE,
        )
        sql_stripped = re.sub(
            r"(`[^`]+`(?:\.`[^`]+`)*)\s+IS\s+NULL\b",
            r"\1 IS NOT VALUED",
            sql_stripped,
            flags=re.IGNORECASE,
        )

        # Deduplicate column names — N1QL doesn't allow duplicate result names.
        sql_stripped = _deduplicate_select_columns(sql_stripped)

        # Parse expected columns AFTER all SQL fixes for result mapping.
        expected_columns = _parse_select_columns(sql_stripped)

        n1ql, positional_params = self._convert_params(sql_stripped, params)

        # Build QueryOptions, injecting txid when inside a N1QL transaction.
        raw_opts = {}
        if self._wrapper is not None and self._wrapper._txid is not None:
            raw_opts["txid"] = self._wrapper._txid
        opts = QueryOptions(
            positional_parameters=positional_params if positional_params else None,
            scan_consistency=self._scan_consistency,
            metrics=True,
            adhoc=self._adhoc,
            query_context=f"default:`{self._bucket_name}`.`{self._scope_name}`",
            raw=raw_opts if raw_opts else None,
        )

        try:
            result = self._cluster.query(n1ql, opts)
            rows_raw = list(result.rows())
        except Exception as e:
            err_str = str(e)
            err_code = ""
            import re as _re

            _m = _re.search(r"first_error_code': (\d+)", err_str)
            if _m:
                err_code = _m.group(1)

            # Handle missing collections gracefully for DML operations.
            if "KeyspaceNotFoundException" in type(e).__name__ or err_code == "12003":
                if n1ql.strip().upper().startswith(("DELETE", "UPDATE", "SELECT")):
                    self._rows = []
                    self._rowcount = 0
                    return

            # Optional fail-soft for SELECT errors. Disabled by default since
            # treating syntax errors as "no rows" hides real bugs. Enable with
            # OPTIONS["GRACEFUL_QUERY_ERRORS"]=True only if running data
            # migrations that intentionally produce some unsupported queries.
            #   3000 = N1QL syntax error
            #   4210 = correlated subquery in GROUP BY (unsupported N1QL pattern)
            if (
                self._graceful_query_errors
                and err_code in ("3000", "4210")
                and n1ql.strip().upper().startswith("SELECT")
            ):
                import logging
                import re as _re_log

                # Redact WHERE clause params from logged query to avoid exposing
                # sensitive data (usernames, emails, etc.) in log files.
                redacted = _re_log.sub(r"\$\d+", "$?", n1ql[:200])
                logging.getLogger("django.db.backends.couchbase").error(
                    "N1QL error %s: unsupported query pattern — returning empty "
                    "result (GRACEFUL_QUERY_ERRORS=True). Query: %s",
                    err_code,
                    redacted,
                )
                self._rows = []
                self._rowcount = 0
                return

            raise

        # Convert dict rows to tuples, preserving SELECT column order.
        if rows_raw:
            if isinstance(rows_raw[0], dict):
                if expected_columns:
                    # Use the parsed SELECT order.
                    columns = expected_columns
                else:
                    # Fallback to dict key order (for SELECT * etc.).
                    columns = list(rows_raw[0].keys())

                self._description = [(col, None, None, None, None, None, None) for col in columns]
                self._rows = [tuple(self._normalize_value(row.get(col)) for col in columns) for row in rows_raw]
            else:
                self._rows = [row if isinstance(row, tuple) else (row,) for row in rows_raw]
        else:
            self._rows = []

        try:
            meta = result.metadata()
            metrics = meta.metrics()
            mc = getattr(metrics, "mutation_count", None)
            if callable(mc):
                mc = mc()
            if mc is not None and int(mc) > 0:
                self._rowcount = int(mc)
            else:
                self._rowcount = len(self._rows)
        except Exception as e:
            import logging

            logging.getLogger("django.db.backends.couchbase").debug(
                "Could not extract query metrics (falling back to row count): %s", e
            )
            self._rowcount = len(self._rows)

    def _fix_bare_table_names(self, sql: str) -> str:
        """Fix DML statements that use bare table names without keyspace prefix.

        Raw SQL from Django migrations (RunSQL) may use bare table names
        like `UPDATE table SET ...`. We add the full keyspace prefix.
        Also quotes N1QL reserved words used as field identifiers.
        """
        # N1QL reserved words that conflict when used as field names.
        n1ql_field_reserved = {
            "path",
            "value",
            "type",
            "index",
            "key",
            "order",
            "offset",
            "limit",
            "role",
            "scope",
            "level",
            "depth",
        }
        # SQL keywords that should NOT be quoted.
        sql_keywords = {
            "set",
            "where",
            "and",
            "or",
            "not",
            "in",
            "from",
            "select",
            "update",
            "delete",
            "insert",
            "into",
            "values",
            "as",
            "on",
            "join",
            "inner",
            "left",
            "right",
            "outer",
            "having",
            "group",
            "by",
            "order",
            "asc",
            "desc",
            "limit",
            "offset",
            "null",
            "is",
            "between",
            "like",
            "distinct",
            "count",
            "sum",
            "avg",
            "min",
            "max",
            "length",
            "true",
            "false",
        }

        def quote_field_identifiers(text):
            """Quote field names that are N1QL reserved words."""

            def replacer(m):
                word = m.group(0)
                wl = word.lower()
                if wl in n1ql_field_reserved and wl not in sql_keywords and not word.startswith("`"):
                    return f"`{word}`"
                return word

            return re.sub(r"(?<![`.\w])(\w+)(?=\s*[=!<>]|\s*\)|\s*,)", replacer, text)

        # Fix UPDATE with bare table name.
        update_match = re.match(r"(UPDATE\s+)(`?\w+`?)(\s+SET\s+)", sql, re.IGNORECASE)
        if update_match:
            table = update_match.group(2).strip("`")
            if "." not in table:
                keyspace = f"`{self._bucket_name}`.`{self._scope_name}`.`{table}`"
                rest = sql[update_match.end() :]
                rest = quote_field_identifiers(rest)
                return f"UPDATE {keyspace} SET {rest}"

        # Fix DELETE with bare table name.
        delete_match = re.match(r"(DELETE\s+FROM\s+)(`?\w+`?)(\s)", sql, re.IGNORECASE)
        if delete_match:
            table = delete_match.group(2).strip("`")
            if "." not in table and self._bucket_name not in table:
                keyspace = f"`{self._bucket_name}`.`{self._scope_name}`.`{table}`"
                rest = sql[delete_match.end() :]
                return f"DELETE FROM {keyspace} {rest}"

        # Fix SELECT with bare table name in FROM — but only for the first
        # FROM that doesn't already have a keyspace.
        select_from_match = re.search(r"(\bFROM\s+)(`?\w+`?)(\s|$)", sql, re.IGNORECASE)
        if select_from_match:
            table = select_from_match.group(2).strip("`")
            if (
                "." not in table
                and table.lower() not in ("system", "dual")
                and self._bucket_name not in sql[: select_from_match.start()]
            ):
                keyspace = f"`{self._bucket_name}`.`{self._scope_name}`.`{table}`"
                sql = (
                    sql[: select_from_match.start()]
                    + f"FROM {keyspace}"
                    + sql[select_from_match.end() - len(select_from_match.group(3)) :]
                )

        return sql

    def executemany(self, sql: str, param_list: list[tuple | list]):
        """Execute the same query with different parameter sets."""
        for params in param_list:
            self.execute(sql, params)

    def fetchone(self) -> tuple | None:
        if self._row_index >= len(self._rows):
            return None
        row = self._rows[self._row_index]
        self._row_index += 1
        return row

    def fetchmany(self, size: int | None = None) -> list[tuple]:
        if size is None:
            size = 1
        end = min(self._row_index + size, len(self._rows))
        rows = self._rows[self._row_index : end]
        self._row_index = end
        return rows

    def fetchall(self) -> list[tuple]:
        rows = self._rows[self._row_index :]
        self._row_index = len(self._rows)
        return rows

    def close(self):
        self._closed = True
        self._rows = []

    def __iter__(self):
        return iter(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
