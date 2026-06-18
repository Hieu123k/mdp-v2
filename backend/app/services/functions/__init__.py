"""prompt 27: server-side aggregation for the outbound endpoint (``/api/outbound/{model}?function=...``).

A small registry of read-only primitives (aggregate / timeseries / top / aging / breakdown) that run a
single SELECT over the model's data source (the matview, the Type A table, or the Type B read-through —
resolved by ``outbound_service.outbound_source_relation``). Safety (🔴):
- the function name + ``agg`` + ``bucket`` are whitelisted;
- every ``group_by`` / ``measure`` / ``date_col`` / ``where`` column is validated against the model's
  EXPOSED columns (and ``validate_identifier``-d + quoted) — never interpolated raw;
- all VALUES (limit, from/to, where-value) are bound parameters;
- only one SELECT is ever built (no other statements possible);
- a bad param raises ``FunctionError`` → 400/422 with a clear message, never leaking SQL.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.data_model import DataModel
from app.services.outbound_service import normalize_row, outbound_source_relation
from app.services.table_generator import TableGenerationError, quote_identifier, validate_identifier

ALLOWED_AGG = {"sum", "avg", "count"}
ALLOWED_BUCKET = {"day", "month"}
NUMERIC_TYPES = {"integer", "float"}
DATE_TYPES = {"date", "datetime"}
MAX_LIMIT = 1000
# longest operators first so "!=" / ">=" / "<=" are matched before "=" / ">" / "<"
WHERE_OPS = ("!=", ">=", "<=", "=", ">", "<")


class FunctionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---- safe param helpers (every column is checked against the model's exposed attributes) ----
def _col(name: str | None, attrs: dict[str, dict[str, Any]], *, label: str) -> str:
    if not name:
        raise FunctionError(f"{label} is required")
    if name not in attrs:
        raise FunctionError(f"{label} '{name}' is not an exposed column of this model", status_code=422)
    try:
        validate_identifier(name, label)
    except TableGenerationError as exc:
        raise FunctionError(str(exc), status_code=422) from exc
    return quote_identifier(name)


def _measure(params: dict[str, str], attrs: dict[str, dict[str, Any]], *, required: bool = True) -> str | None:
    name = params.get("measure")
    if not name:
        if required:
            raise FunctionError("measure is required")
        return None
    qname = _col(name, attrs, label="measure")
    if attrs[name]["data_type"] not in NUMERIC_TYPES:
        raise FunctionError(f"measure '{name}' must be numeric (integer/float)", status_code=422)
    return qname


def _date_col(params: dict[str, str], attrs: dict[str, dict[str, Any]]) -> str:
    name = params.get("date_col")
    qname = _col(name, attrs, label="date_col")
    if attrs[name]["data_type"] not in DATE_TYPES:
        raise FunctionError(f"date_col '{name}' must be a date/datetime column", status_code=422)
    return qname


def _group_by(params: dict[str, str], attrs: dict[str, dict[str, Any]]) -> list[str]:
    raw = params.get("group_by") or ""
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    if not cols:
        raise FunctionError("group_by is required")
    return [_col(c, attrs, label="group_by") for c in cols]


def _agg(params: dict[str, str], *, default: str = "sum") -> str:
    agg = (params.get("agg") or default).lower()
    if agg not in ALLOWED_AGG:
        raise FunctionError(f"agg must be one of {sorted(ALLOWED_AGG)}")
    return agg


def _limit(params: dict[str, str], *, default: int = MAX_LIMIT) -> int:
    raw = params.get("limit")
    if raw is None or raw == "":
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise FunctionError("limit must be an integer") from exc
    if n < 1:
        raise FunctionError("limit must be >= 1")
    return min(n, MAX_LIMIT)


def _agg_expr(agg: str, measure_q: str | None) -> str:
    if agg == "count":
        return "COUNT(*)"
    # round to 2 dp + cast to float so the JSON value is clean (Postgres)
    return f"ROUND({agg.upper()}({measure_q})::numeric, 2)::double precision"


def _time_filter(params: dict[str, str], date_col_q: str, out: dict[str, Any]) -> list[str]:
    clauses: list[str] = []
    if params.get("from"):
        out["fn_from"] = params["from"]
        clauses.append(f"{date_col_q} >= :fn_from")
    if params.get("to"):
        out["fn_to"] = params["to"]
        clauses.append(f"{date_col_q} <= :fn_to")
    return clauses


def _parse_where(raw: str | None, attrs: dict[str, dict[str, Any]], out: dict[str, Any]) -> str | None:
    """Parse a single safe condition ``<column><op><value>`` (op ∈ WHERE_OPS). Column whitelisted, value
    is a BOUND parameter — no raw value ever reaches the SQL."""
    if not raw:
        return None
    for op in WHERE_OPS:
        if op in raw:
            col, _, val = raw.partition(op)
            col_q = _col(col.strip(), attrs, label="where column")
            out["fn_w"] = val.strip()
            sql_op = "<>" if op == "!=" else op
            return f"{col_q} {sql_op} :fn_w"
    raise FunctionError("where must be <column><op><value> (op: = != < <= > >=)")


def _run(db: Session, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows = db.execute(text(sql), params).mappings().all()
    return [normalize_row(dict(row)) for row in rows]


# ---- the 5 primitives ----
def _aggregate(db, model, src, attrs, params):
    agg = _agg(params)
    group = _group_by(params, attrs)
    measure_q = _measure(params, attrs, required=(agg != "count"))
    p: dict[str, Any] = {}
    where = _time_filter(params, _date_col(params, attrs), p) if params.get("date_col") else []
    sql = f"SELECT {', '.join(group)}, {_agg_expr(agg, measure_q)} AS value FROM {src}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    p["fn_limit"] = _limit(params)
    sql += f" GROUP BY {', '.join(group)} ORDER BY value DESC NULLS LAST LIMIT :fn_limit"
    return _run(db, sql, p)


def _timeseries(db, model, src, attrs, params):
    agg = _agg(params)
    measure_q = _measure(params, attrs, required=(agg != "count"))
    date_q = _date_col(params, attrs)
    bucket = (params.get("bucket") or "month").lower()
    if bucket not in ALLOWED_BUCKET:
        raise FunctionError("bucket must be one of day|month")
    p: dict[str, Any] = {}
    where = _time_filter(params, date_q, p)
    sql = (
        f"SELECT date_trunc('{bucket}', {date_q})::date AS bucket, "
        f"{_agg_expr(agg, measure_q)} AS value FROM {src}"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY 1 ORDER BY 1"
    return _run(db, sql, p)


def _top(db, model, src, attrs, params):
    group = _group_by(params, attrs)
    measure_q = _measure(params, attrs)
    agg = _agg(params, default="sum")
    p = {"fn_limit": _limit(params, default=10)}
    sql = (
        f"SELECT {', '.join(group)}, {_agg_expr(agg, measure_q)} AS value FROM {src} "
        f"GROUP BY {', '.join(group)} ORDER BY value DESC NULLS LAST LIMIT :fn_limit"
    )
    return _run(db, sql, p)


def _aging(db, model, src, attrs, params):
    date_q = _date_col(params, attrs)
    measure_q = _measure(params, attrs)
    raw_buckets = params.get("buckets") or "30,60,90"
    try:
        bounds = sorted({int(x) for x in raw_buckets.split(",") if x.strip()})
    except ValueError as exc:
        raise FunctionError("buckets must be comma-separated integers, e.g. 30,60,90") from exc
    if not bounds or any(b <= 0 for b in bounds):
        raise FunctionError("buckets must be positive integers")
    p: dict[str, Any] = {}
    where = [f"current_date >= {date_q}::date"]  # only past-due rows
    extra = _parse_where(params.get("where"), attrs, p)
    if extra:
        where.append(extra)
    cases, prev = [], 0
    for b in bounds:  # b are validated ints -> safe to inline
        cases.append(f"WHEN current_date - {date_q}::date <= {b} THEN '{prev}-{b}'")
        prev = b
    case_sql = "CASE " + " ".join(cases) + f" ELSE '{bounds[-1]}+' END"
    sql = (
        f"SELECT {case_sql} AS bucket, {_agg_expr('sum', measure_q)} AS value FROM {src} "
        f"WHERE {' AND '.join(where)} GROUP BY 1 ORDER BY 1"
    )
    return _run(db, sql, p)


def _breakdown(db, model, src, attrs, params):
    group = _group_by(params, attrs)
    p = {"fn_limit": _limit(params)}
    sql = (
        f"SELECT {', '.join(group)}, COUNT(*) AS count FROM {src} "
        f"GROUP BY {', '.join(group)} ORDER BY count DESC LIMIT :fn_limit"
    )
    rows = _run(db, sql, p)
    total = sum(int(r["count"]) for r in rows) or 1
    for r in rows:
        r["ratio"] = round(int(r["count"]) / total, 4)
    return rows


REGISTRY: dict[str, Callable] = {
    "aggregate": _aggregate,
    "timeseries": _timeseries,
    "top": _top,
    "aging": _aging,
    "breakdown": _breakdown,
}


def run_function(db: Session, *, model: DataModel, function: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Dispatch + run a whitelisted aggregation primitive over ``model``'s data. Raises FunctionError
    (400/422) on any unknown function or invalid/non-exposed column/param."""
    handler = REGISTRY.get(function)
    if handler is None:
        raise FunctionError(f"unknown function '{function}'; allowed: {sorted(REGISTRY)}")
    src, attrs = outbound_source_relation(db, model)
    return handler(db, model, src, attrs, params)
