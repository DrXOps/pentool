"""Filter engine — a universal table filtering system.

Layers:
    FilterOp          — operator enum
    FilterPredicate   — one predicate (field + operator + value)
    FilterSpec        — a set of predicates with AND/OR logic
    ColumnFilter      — description of a filter UI field

FilterSpec can:
    - to_sql()  → (WHERE clause, params) for SQL filtering
    - apply()   → filter a list of dicts in memory
    - to_dict() / from_dict() — serialisation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Operators ──────────────────────────────────────────────────────────────


class FilterOp(str, Enum):
    """Comparison operator of a single predicate."""

    EQ = "eq"  # field = ?
    NEQ = "neq"  # field != ?
    GT = "gt"  # field > ?
    GTE = "gte"  # field >= ?
    LT = "lt"  # field < ?
    LTE = "lte"  # field <= ?
    BETWEEN = "between"  # field BETWEEN ? AND ?
    LIKE = "like"  # field LIKE '%value%'
    STARTS = "starts"  # field LIKE 'value%'
    IN = "in"  # field IN (?, ?, ...)
    REGEX = "regex"  # field REGEXP ?
    IS_NULL = "is_null"  # field IS NULL
    NOT_NULL = "not_null"  # field IS NOT NULL
    HAS = "has"  # for tags: field CONTAINS value
    FTS = "fts"  # FTS5 full-text search (special-cased)


# ── Predicate ───────────────────────────────────────────────────────────────


@dataclass
class FilterPredicate:
    """A single filter predicate: field operator value.

    Examples:
        FilterPredicate("host", FilterOp.LIKE, "example.com")
        FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299))
        FilterPredicate("method", FilterOp.IN, ["GET", "POST"])
    """

    field: str
    operator: FilterOp
    value: Any

    # ── SQL ────────────────────────────────────────────────────────────────

    def to_sql(self) -> tuple[str, list]:
        """Build (clause, params) for a SQL WHERE clause.

        Returns ("", []) for operators that need special handling (FTS, etc.).
        """
        match self.operator:
            case FilterOp.EQ:
                return (f"{self.field} = ?", [self.value])

            case FilterOp.NEQ:
                return (f"{self.field} != ?", [self.value])

            case FilterOp.GT:
                return (f"{self.field} > ?", [self.value])

            case FilterOp.GTE:
                return (f"{self.field} >= ?", [self.value])

            case FilterOp.LT:
                return (f"{self.field} < ?", [self.value])

            case FilterOp.LTE:
                return (f"{self.field} <= ?", [self.value])

            case FilterOp.BETWEEN:
                lo, hi = self.value
                return (f"{self.field} BETWEEN ? AND ?", [lo, hi])

            case FilterOp.LIKE:
                return (f"{self.field} LIKE ?", [f"%{self.value}%"])

            case FilterOp.STARTS:
                return (f"{self.field} LIKE ?", [f"{self.value}%"])

            case FilterOp.IN:
                values = list(self.value) if isinstance(self.value, (list, tuple)) else [self.value]
                # Special case: "hosts" field — expand with port variants
                if self.field == "hosts":
                    sub = " OR ".join("(host = ? OR host LIKE ?)" for _ in values)
                    p: list = []
                    for h in values:
                        base = str(h).split(":")[0]
                        p.append(base)
                        p.append(f"{base}:%")
                    return (f"({sub})", p)
                placeholders = ",".join("?" for _ in values)
                return (f"{self.field} IN ({placeholders})", values)

            case FilterOp.REGEX:
                return (f"{self.field} REGEXP ?", [self.value])

            case FilterOp.IS_NULL:
                return (f"COALESCE({self.field}, '') = ''", [])

            case FilterOp.NOT_NULL:
                return (f"COALESCE({self.field}, '') != ''", [])

            case FilterOp.HAS:
                # Tags: match a tag inside comma-separated list
                tag = self.value
                return (
                    f"({self.field} = ? OR {self.field} LIKE ? OR {self.field} LIKE ? OR {self.field} LIKE ?)",
                    [tag, f"{tag},%", f"%,{tag},%", f"%,{tag}"],
                )

            case FilterOp.FTS:
                return ("", [])  # handled separately by storage

    # ── In-memory ──────────────────────────────────────────────────────────

    def apply(self, row: dict) -> bool:
        """Check if a row dict satisfies this predicate."""
        actual = row.get(self.field)

        # IS_NULL / NOT_NULL are handled before the None check
        if self.operator == FilterOp.IS_NULL:
            return actual is None or actual == ""
        if self.operator == FilterOp.NOT_NULL:
            return actual is not None and actual != ""

        if actual is None:
            return False

        match self.operator:
            case FilterOp.EQ:
                return actual == self.value
            case FilterOp.NEQ:
                return actual != self.value
            case FilterOp.GT:
                return actual > self.value
            case FilterOp.GTE:
                return actual >= self.value
            case FilterOp.LT:
                return actual < self.value
            case FilterOp.LTE:
                return actual <= self.value
            case FilterOp.BETWEEN:
                lo, hi = self.value
                return lo <= actual <= hi
            case FilterOp.LIKE:
                return self.value.lower() in str(actual).lower()
            case FilterOp.STARTS:
                return str(actual).lower().startswith(self.value.lower())
            case FilterOp.IN:
                return actual in self.value
            case FilterOp.REGEX:
                import re

                try:
                    return bool(re.search(self.value, str(actual), re.IGNORECASE))
                except re.error:
                    return False
            case FilterOp.IS_NULL:
                return actual is None or actual == ""
            case FilterOp.NOT_NULL:
                return actual is not None and actual != ""
            case FilterOp.HAS:
                return self.value in str(actual).split(",")

        return False  # unknown operator


# ── Predicate set ───────────────────────────────────────────────────────


@dataclass
class FilterSpec:
    """A set of filter predicates.

    Args:
        predicates: list of predicates
        logic: "AND" or "OR" — how to combine the predicates
    """

    predicates: list[FilterPredicate] = field(default_factory=list)
    logic: str = "AND"

    # ── SQL ────────────────────────────────────────────────────────────────

    def to_sql(self) -> tuple[str, list]:
        """Build a full WHERE clause + params from all predicates.

        Returns ("", []) when empty or no SQL-able predicates.
        SQL-able predicates are all except FTS.
        """
        clauses: list[str] = []
        params: list = []

        for p in self.predicates:
            if p.operator == FilterOp.FTS:
                continue  # FTS5 handled by storage, not here
            clause, p_params = p.to_sql()
            if clause:
                clauses.append(clause)
                params.extend(p_params)

        if not clauses:
            return "", []

        joiner = f" {self.logic} "
        return f"WHERE {joiner.join(clauses)}", params

    @property
    def fts_query(self) -> str | None:
        """Extract the FTS search term, if present."""
        for p in self.predicates:
            if p.operator == FilterOp.FTS:
                return str(p.value)
        return None

    @property
    def is_empty(self) -> bool:
        return len(self.predicates) == 0

    # ── In-memory ──────────────────────────────────────────────────────────

    def apply(self, rows: list[dict]) -> list[dict]:
        """Filter rows in-memory."""
        if not self.predicates:
            return rows

        if self.logic == "AND":
            for p in self.predicates:
                rows = [r for r in rows if p.apply(r)]
            return rows

        # OR logic
        return [r for r in rows if any(p.apply(r) for p in self.predicates)]

    # ── Serialisation ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "logic": self.logic,
            "predicates": [{"field": p.field, "operator": p.operator.value, "value": p.value} for p in self.predicates],
        }

    @classmethod
    def from_dict(cls, d: dict) -> FilterSpec:
        predicates = [
            FilterPredicate(
                field=p["field"],
                operator=FilterOp(p["operator"]),
                value=p["value"],
            )
            for p in d.get("predicates", [])
        ]
        return cls(predicates=predicates, logic=d.get("logic", "AND"))


# ── Filter UI field description ────────────────────────────────────────────


class FilterFieldType(str, Enum):
    """UI control type of a filter field."""

    TEXT = "text"  # Input (text)
    NUMBER = "number"  # Input (number)
    SELECT = "select"  # Select/Dropdown
    CYCLER = "cycler"  # cyclic switcher (Any → GET → POST → ...)
    TOGGLE = "toggle"  # on/off
    RANGE = "range"  # two Inputs (from, to)


@dataclass
class FilterField:
    """Description of a single filter field in FilterBar.

    Lets FilterBarWidget configure its UI without hard-coded widgets.

    Attributes:
        id:         DOM id of the widget (fb-{name})
        label:      label text ("Host:", "Status:")
        field_type: UI control type
        field:      column name in the data/DB ("host", "status_code")
        operator:   default comparison operator
        options:    options for CYCLER/SELECT [(label, value), ...]
        placeholder: placeholder for TEXT/NUMBER
    """

    id: str
    label: str
    field_type: FilterFieldType
    field: str
    operator: FilterOp
    options: list[tuple[str, Any]] | None = None
    placeholder: str = ""
