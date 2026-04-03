"""DB-API 2.0 compatible cursor for Couchbase N1QL queries."""

from __future__ import annotations

import re
from typing import Any

from couchbase.options import QueryOptions

# Pattern to extract column names/aliases from a SELECT clause.
_SELECT_COLUMNS_RE = re.compile(
    r"SELECT\s+(?:DISTINCT\s+)?(.*?)\s+FROM\s+",
    re.IGNORECASE | re.DOTALL,
)


def _parse_select_columns(sql: str) -> list[str] | None:
    """Extract the expected column order from a SELECT statement.

    Returns a list of column names/aliases in SELECT order, or None if
    the SELECT clause cannot be parsed (e.g., SELECT *).
    """
    m = _SELECT_COLUMNS_RE.match(sql.strip())
    if not m:
        return None

    select_part = m.group(1).strip()
    if select_part == "*" or select_part.endswith(".*"):
        return None

    columns = []
    # Simple parser: split by comma, handling parentheses for functions.
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
        backtick_match = re.search(r'`(\w+)`\s*$', col_expr)
        if backtick_match:
            result.append(backtick_match.group(1))
            continue

        # Handle dotted: d.col_name -> col_name
        dot_match = re.search(r'\.(\w+)\s*$', col_expr)
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
                    # Check if DISTINCT is present
                    if select_part.upper().startswith("DISTINCT "):
                        select_part = "DISTINCT " + select_part[9:]
                        result.append(f"SELECT RAW {select_part} {rest}")
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

    def __init__(self, cluster, bucket_name, scope_name="_default"):
        self._cluster = cluster
        self._bucket_name = bucket_name
        self._scope_name = scope_name
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
        # Find all IN (%s, %s, ...) patterns.
        in_pattern = re.compile(r'\bIN\s*\((%s(?:\s*,\s*%s)*)\)', re.IGNORECASE)

        new_params = []
        param_index = 0
        last_end = 0
        result_parts = []

        for match in in_pattern.finditer(sql):
            # Count how many %s are in this IN clause.
            in_content = match.group(1)
            placeholder_count = in_content.count("%s")

            # Add everything before this match, consuming params along the way.
            before = sql[last_end:match.start()]
            before_count = before.count("%s")
            for i in range(before_count):
                new_params.append(params[param_index])
                param_index += 1
            result_parts.append(before)

            # Collect the IN values into an array.
            array_values = params[param_index:param_index + placeholder_count]
            param_index += placeholder_count
            new_params.append(list(array_values))
            result_parts.append("IN %s")

            last_end = match.end()

        if not result_parts:
            # No IN clauses found — return unchanged.
            return sql, params

        # Add the remainder.
        remainder = sql[last_end:]
        remainder_count = remainder.count("%s")
        for i in range(remainder_count):
            new_params.append(params[param_index])
            param_index += 1
        result_parts.append(remainder)

        return "".join(result_parts), new_params

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

        # Parse expected column order from SELECT clause before param conversion.
        expected_columns = _parse_select_columns(sql_stripped)

        # Fix positional ORDER BY and GROUP BY — N1QL doesn't support
        # positional references like ORDER BY 1 or GROUP BY 1, 2, 3.
        sql_stripped = _fix_positional_order_by(sql_stripped, expected_columns)
        sql_stripped = _fix_positional_group_by(sql_stripped, expected_columns)

        # Fix IN (SELECT ...) subqueries — N1QL needs SELECT RAW for scalars.
        sql_stripped = _fix_in_subquery(sql_stripped)

        n1ql, positional_params = self._convert_params(sql_stripped, params)

        opts = QueryOptions(
            positional_parameters=positional_params if positional_params else None,
            scan_consistency="request_plus",
            metrics=True,
        )

        try:
            result = self._cluster.query(n1ql, opts)
            rows_raw = list(result.rows())
        except Exception as e:
            # Handle missing collections gracefully for DML operations.
            err_str = str(e)
            if "KeyspaceNotFoundException" in type(e).__name__ or "12003" in err_str:
                if n1ql.strip().upper().startswith(("DELETE", "UPDATE", "SELECT")):
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

                self._description = [
                    (col, None, None, None, None, None, None) for col in columns
                ]
                self._rows = [
                    tuple(row.get(col) for col in columns) for row in rows_raw
                ]
            else:
                self._rows = [
                    row if isinstance(row, tuple) else (row,) for row in rows_raw
                ]
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
        except Exception:
            self._rowcount = len(self._rows)

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
        rows = self._rows[self._row_index:end]
        self._row_index = end
        return rows

    def fetchall(self) -> list[tuple]:
        rows = self._rows[self._row_index:]
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
