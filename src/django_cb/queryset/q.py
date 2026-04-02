"""Q objects for building complex query expressions with AND, OR, NOT."""

from __future__ import annotations

from typing import Any

from django_cb.query.n1ql import N1QLQuery
from django_cb.queryset.transform import apply_lookup


class Q:
    """A query expression node that can be combined with & (AND), | (OR), and ~ (NOT).

    Usage:
        Q(name="Alice") & Q(age__gte=18)
        Q(status="active") | Q(role="admin")
        ~Q(deleted=True)
        Q(age__gte=18, status="active")  # multiple kwargs = AND
    """

    AND = "AND"
    OR = "OR"

    def __init__(self, **kwargs):
        self.children: list[Q | tuple[str, Any]] = []
        self.connector: str = self.AND
        self.negated: bool = False

        # Each kwarg becomes a leaf node
        for key, value in kwargs.items():
            self.children.append((key, value))

    def _combine(self, other: Q, connector: str) -> Q:
        """Combine two Q objects with the given connector."""
        if not isinstance(other, Q):
            raise TypeError(f"Cannot combine Q with {type(other).__name__}")
        combined = Q()
        combined.connector = connector
        combined.children = [self, other]
        return combined

    def __and__(self, other: Q) -> Q:
        return self._combine(other, self.AND)

    def __or__(self, other: Q) -> Q:
        return self._combine(other, self.OR)

    def __invert__(self) -> Q:
        negated = Q()
        negated.children = self.children[:]
        negated.connector = self.connector
        negated.negated = not self.negated
        return negated

    def __repr__(self) -> str:
        if self.children and all(isinstance(c, tuple) for c in self.children):
            parts = [f"{k}={v!r}" for k, v in self.children]
            prefix = "~" if self.negated else ""
            return f"{prefix}Q({', '.join(parts)})"
        prefix = "~" if self.negated else ""
        return f"{prefix}Q({f' {self.connector} '.join(repr(c) for c in self.children)})"

    def resolve(self, query: N1QLQuery, field_map: dict[str, str] | None = None) -> str:
        """Resolve this Q tree into a N1QL WHERE clause fragment.

        Args:
            query: The N1QLQuery to add parameters to.
            field_map: Optional mapping of Python field names to DB field names.

        Returns:
            A WHERE clause string.
        """
        if not self.children:
            return ""

        parts = []
        for child in self.children:
            if isinstance(child, Q):
                resolved = child.resolve(query, field_map)
                if resolved:
                    parts.append(resolved)
            elif isinstance(child, tuple):
                field_expr, value = child
                # Map Python field names to DB field names if provided
                if field_map:
                    base_field = field_expr.split("__")[0]
                    if base_field in field_map and field_map[base_field] != base_field:
                        field_expr = field_map[base_field] + field_expr[len(base_field) :]
                clause = apply_lookup(query, field_expr, value)
                parts.append(clause)

        if not parts:
            return ""

        if len(parts) == 1:
            result = parts[0]
        else:
            joiner = f" {self.connector} "
            result = f"({joiner.join(parts)})"

        if self.negated:
            result = f"NOT ({result})"

        return result
