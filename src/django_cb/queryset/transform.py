"""Transform Django-style field lookups into N1QL WHERE clause fragments.

Converts expressions like field__gte=18 into N1QL: d.`field` >= $N
"""

from __future__ import annotations

from typing import Any

from django_cb.query.n1ql import N1QLQuery

# Map of lookup suffix -> handler function
# Each handler takes (query, db_field, value) and returns a WHERE clause string
LOOKUP_TRANSFORMS: dict[str, Any] = {}


def register_lookup(name: str):
    """Decorator to register a lookup transform."""

    def decorator(func):
        LOOKUP_TRANSFORMS[name] = func
        return func

    return decorator


def parse_lookup(field_expr: str) -> tuple[str, str]:
    """Parse a field expression like 'name__contains' into ('name', 'contains').

    If no lookup is specified, defaults to 'exact'.
    """
    parts = field_expr.split("__")
    if len(parts) == 1:
        return parts[0], "exact"

    # Check if the last part is a known lookup
    candidate = parts[-1]
    if candidate in LOOKUP_TRANSFORMS:
        return "__".join(parts[:-1]), candidate

    # Could be a nested field path (e.g., address__city), default to exact
    return field_expr, "exact"


def apply_lookup(query: N1QLQuery, field_expr: str, value: Any) -> str:
    """Apply a lookup transform to generate a WHERE clause fragment.

    Args:
        query: The N1QLQuery to add parameters to.
        field_expr: The Django-style field expression (e.g., 'age__gte').
        value: The value to compare against.

    Returns:
        A WHERE clause fragment string.
    """
    field_name, lookup = parse_lookup(field_expr)
    if lookup not in LOOKUP_TRANSFORMS:
        raise ValueError(f"Unknown lookup type: '{lookup}'")
    return LOOKUP_TRANSFORMS[lookup](query, field_name, value)


# ============================================================
# Lookup implementations
# ============================================================


@register_lookup("exact")
def lookup_exact(query: N1QLQuery, field: str, value: Any) -> str:
    if value is None:
        return f"d.`{field}` IS NULL"
    placeholder = query.add_param(value)
    return f"d.`{field}` = {placeholder}"


@register_lookup("ne")
def lookup_ne(query: N1QLQuery, field: str, value: Any) -> str:
    if value is None:
        return f"d.`{field}` IS NOT NULL"
    placeholder = query.add_param(value)
    return f"d.`{field}` != {placeholder}"


@register_lookup("gt")
def lookup_gt(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"d.`{field}` > {placeholder}"


@register_lookup("gte")
def lookup_gte(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"d.`{field}` >= {placeholder}"


@register_lookup("lt")
def lookup_lt(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"d.`{field}` < {placeholder}"


@register_lookup("lte")
def lookup_lte(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"d.`{field}` <= {placeholder}"


@register_lookup("in")
def lookup_in(query: N1QLQuery, field: str, value: Any) -> str:
    if not isinstance(value, (list, tuple, set)):
        raise ValueError(f"'in' lookup requires a list/tuple/set, got {type(value).__name__}")
    placeholder = query.add_param(list(value))
    return f"d.`{field}` IN {placeholder}"


@register_lookup("contains")
def lookup_contains(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"CONTAINS(d.`{field}`, {placeholder})"


@register_lookup("icontains")
def lookup_icontains(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(str(value).lower())
    return f"CONTAINS(LOWER(d.`{field}`), {placeholder})"


@register_lookup("startswith")
def lookup_startswith(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(str(value) + "%")
    return f"d.`{field}` LIKE {placeholder}"


@register_lookup("istartswith")
def lookup_istartswith(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(str(value).lower() + "%")
    return f"LOWER(d.`{field}`) LIKE {placeholder}"


@register_lookup("endswith")
def lookup_endswith(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param("%" + str(value))
    return f"d.`{field}` LIKE {placeholder}"


@register_lookup("iendswith")
def lookup_iendswith(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param("%" + str(value).lower())
    return f"LOWER(d.`{field}`) LIKE {placeholder}"


@register_lookup("isnull")
def lookup_isnull(query: N1QLQuery, field: str, value: Any) -> str:
    if value:
        return f"d.`{field}` IS NULL"
    return f"d.`{field}` IS NOT NULL"


@register_lookup("regex")
def lookup_regex(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(value)
    return f"REGEXP_CONTAINS(d.`{field}`, {placeholder})"


@register_lookup("iregex")
def lookup_iregex(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(f"(?i){value}")
    return f"REGEXP_CONTAINS(d.`{field}`, {placeholder})"


@register_lookup("between")
def lookup_between(query: N1QLQuery, field: str, value: Any) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("'between' lookup requires a list/tuple of exactly 2 values")
    p1 = query.add_param(value[0])
    p2 = query.add_param(value[1])
    return f"d.`{field}` BETWEEN {p1} AND {p2}"


@register_lookup("iexact")
def lookup_iexact(query: N1QLQuery, field: str, value: Any) -> str:
    placeholder = query.add_param(str(value).lower())
    return f"LOWER(d.`{field}`) = {placeholder}"
