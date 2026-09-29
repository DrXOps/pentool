"""Filter engine — универсальная система фильтрации таблиц.

Слои:
    FilterOp          — enum операторов
    FilterPredicate   — один предикат (поле + оператор + значение)
    FilterSpec        — набор предикатов с AND/OR-логикой
    ColumnFilter      — описание UI-поля фильтрации

FilterSpec умеет:
    - to_sql()  → (WHERE clause, params) для SQL-фильтрации
    - apply()   → фильтровать список dict'ов in-memory
    - to_dict() / from_dict() — сериализация
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# ── Операторы ──────────────────────────────────────────────────────────────


class FilterOp(str, Enum):
    """Оператор сравнения для одного предиката."""

    EQ = "eq"               # field = ?
    NEQ = "neq"             # field != ?
    GT = "gt"               # field > ?
    GTE = "gte"             # field >= ?
    LT = "lt"               # field < ?
    LTE = "lte"             # field <= ?
    BETWEEN = "between"     # field BETWEEN ? AND ?
    LIKE = "like"           # field LIKE '%value%'
    STARTS = "starts"       # field LIKE 'value%'
    IN = "in"               # field IN (?, ?, ...)
    REGEX = "regex"         # field REGEXP ?
    IS_NULL = "is_null"     # field IS NULL
    NOT_NULL = "not_null"   # field IS NOT NULL
    HAS = "has"             # for tags: field CONTAINS value
    FTS = "fts"             # FTS5 full-text search (спецобработка)


# ── Предикат ───────────────────────────────────────────────────────────────


@dataclass
class FilterPredicate:
    """Один предикат фильтрации: field operator value.

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
                    f"({self.field} = ? OR {self.field} LIKE ? OR "
                    f"{self.field} LIKE ? OR {self.field} LIKE ?)",
                    [tag, f"{tag},%", f"%,{tag},%", f"%,{tag}"],
                )

            case FilterOp.FTS:
                return ("", [])  # handled separately by storage

    # ── In-memory ──────────────────────────────────────────────────────────

    def apply(self, row: dict) -> bool:
        """Check if a row dict satisfies this predicate."""
        actual = row.get(self.field)

        # IS_NULL / NOT_NULL обрабатываются до проверки на None
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


# ── Набор предикатов ───────────────────────────────────────────────────────


@dataclass
class FilterSpec:
    """Набор предикатов фильтрации.

    Args:
        predicates: список предикатов
        logic: "AND" или "OR" — как комбинировать предикаты
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

    # ── Сериализация ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "logic": self.logic,
            "predicates": [
                {"field": p.field, "operator": p.operator.value, "value": p.value}
                for p in self.predicates
            ],
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


# ── Описание UI-поля фильтрации ────────────────────────────────────────────


class FilterFieldType(str, Enum):
    """Тип UI-контрола для поля фильтрации."""
    TEXT = "text"           # Input (text)
    NUMBER = "number"       # Input (number)
    SELECT = "select"       # Select/Dropdown
    CYCLER = "cycler"       # Циклический переключатель (Any → GET → POST → ...)
    TOGGLE = "toggle"       # Вкл/Выкл
    RANGE = "range"         # Два Input (from, to)


@dataclass
class FilterField:
    """Описание одного поля фильтрации в FilterBar.

    Позволяет FilterBarWidget сконфигурировать UI без жёсткого кода.

    Attributes:
        id:         DOM id для виджета (fb-{name})
        label:      Текст метки ("Host:", "Status:")
        field_type: Тип UI-контрола
        field:      Имя колонки в данных/БД ("host", "status_code")
        operator:   Оператор сравнения по умолчанию
        options:    Опции для CYCLER/SELECT [(label, value), ...]
        placeholder: Placeholder для TEXT/NUMBER
    """

    id: str
    label: str
    field_type: FilterFieldType
    field: str
    operator: FilterOp
    options: list[tuple[str, Any]] | None = None
    placeholder: str = ""