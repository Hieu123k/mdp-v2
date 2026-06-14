"""Type B Materialized View PoC (prompt 14).

A Type B data model normally reads through to its source tables on every request (live JOIN). When
``matview_enabled`` is set, this service materialises the SAME read-through SELECT into a real Postgres
materialized view in the dedicated ``mdp_models`` schema, so Grafana / outbound can read a single
pre-joined table fast. The matview BODY is generated from the validated Type B plan (the exact query the
outbound read-through runs — one source of truth), never from free-form SQL.

Safety / invariants:
  * Read-only with respect to the source: the matview only SELECTs from the whitelisted source schemas;
    the only writes are CREATE/REFRESH/DROP DDL on ``mdp_models`` (never the source tables).
  * Additive: when the flag is off the model behaves exactly as before (read-through). Dropping the
    matview never touches source data.
  * PostgreSQL-only: materialized views + ``REFRESH ... CONCURRENTLY`` are Postgres features. On any other
    dialect (e.g. the SQLite test DB) these operations raise ``MatviewError`` and are skipped by callers.
  * ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` cannot run inside a transaction block, so all matview DDL
    runs on a dedicated AUTOCOMMIT connection, separate from the ORM session's transaction.
"""

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.data_model import DataModel
from app.services.outbound_service import validate_type_b_outbound_mapping
from app.services.table_generator import quote_identifier, validate_identifier
from app.services.type_b_mapping_service import (
    build_type_b_from_clause,
    type_b_qualified_column,
)

MATVIEW_SCHEMA = "mdp_models"

# Model attribute data_types worth a secondary index for fast time-filter / GROUP BY / category
# lookups (the allowed data_types are text/integer/float/boolean/date/datetime/json). Foreign-key
# columns are also indexed regardless of type (see _secondary_index_columns).
_INDEXABLE_DATA_TYPES = {"date", "datetime", "integer"}
_MAX_SECONDARY_INDEXES = 3
_MAX_IDENTIFIER_LEN = 63  # PostgreSQL identifier limit


class MatviewError(Exception):
    """Materialized-view operation failed (or is unsupported on this dialect)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_postgres(db: Session) -> bool:
    return bool(db.bind and db.bind.dialect.name == "postgresql")


def _truncate_identifier(name: str) -> str:
    return name[:_MAX_IDENTIFIER_LEN]


def matview_qualified_name(model: DataModel) -> str:
    """``"mdp_models"."<model>"`` — both identifiers validated + quoted (injection-safe)."""
    validate_identifier(model.name, "Data model name")
    return f"{quote_identifier(MATVIEW_SCHEMA)}.{quote_identifier(model.name)}"


def _pk_columns(model: DataModel) -> list[str]:
    """The model attribute name(s) forming the unique key — required for the UNIQUE index that
    ``REFRESH ... CONCURRENTLY`` needs and to dedup the matview."""
    pk = [a["name"] for a in model.attributes if a.get("is_primary_key")]
    if not pk and model.primary_key:
        pk = [model.primary_key]
    return pk


def _secondary_index_columns(model: DataModel, validation: dict[str, Any], pk: set[str]) -> list[str]:
    """Heuristic: index the recency/time column + foreign-key / date-time / numeric columns (the
    columns Grafana filters / groups by), excluding the PK, capped at a few."""
    chosen: list[str] = []
    recency = validation.get("recency_column")
    attr_names = {a["name"] for a in model.attributes}
    if recency and recency in attr_names and recency not in pk:
        chosen.append(recency)
    for attr in model.attributes:
        name = attr["name"]
        if name in pk or name in chosen:
            continue
        if attr.get("is_foreign_key") or attr.get("data_type") in _INDEXABLE_DATA_TYPES:
            chosen.append(name)
        if len(chosen) >= _MAX_SECONDARY_INDEXES:
            break
    return chosen


def build_matview_plan(db: Session, model: DataModel) -> dict[str, Any]:
    """Generate the matview body SELECT + index plan from the validated Type B mapping. Pure SQL
    construction (no matview DDL) so it can be unit-tested on any dialect. Raises MatviewError if the
    model is not a Type B model or has no usable unique key."""
    if model.type != "B":
        raise MatviewError("Materialized views are only supported for Type B models.")
    if len(model.name) > _MAX_IDENTIFIER_LEN:
        raise MatviewError(
            f"Model name is too long for a materialized view (max {_MAX_IDENTIFIER_LEN} chars). "
            "Rename the model or keep it as read-through."
        )
    pk = _pk_columns(model)
    if not pk:
        raise MatviewError(
            "Type B model needs a primary key (unique attribute) before its matview can be built "
            "(required for the unique index + REFRESH CONCURRENTLY)."
        )
    validation = validate_type_b_outbound_mapping(db, model)
    from_sql, alias_by_table = build_type_b_from_clause(db, validation)
    mapped_columns = validation["mapped_columns"]
    # Same projection the read-through outbound query uses → the matview is byte-for-byte the read-through.
    select_clause = ", ".join(
        f"{type_b_qualified_column(alias_by_table, col)} AS {quote_identifier(col['attribute'])}"
        for col in mapped_columns
    )
    select_sql = f"SELECT {select_clause} FROM {from_sql}"
    secondary = _secondary_index_columns(model, validation, set(pk))
    for col in [*pk, *secondary]:
        validate_identifier(col, "Matview column")
    return {"select_sql": select_sql, "pk_columns": pk, "secondary_columns": secondary}


def _index_name(model: DataModel, suffix: str) -> str:
    return _truncate_identifier(f"mv_{model.name}_{suffix}")


def _create_matview_ddl(model: DataModel, plan: dict[str, Any]) -> list[str]:
    """The ordered DDL to (re)build the matview from scratch + populate it (non-concurrent)."""
    qname = matview_qualified_name(model)
    pk_cols = ", ".join(quote_identifier(c) for c in plan["pk_columns"])
    stmts = [
        f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(MATVIEW_SCHEMA)}",
        f"DROP MATERIALIZED VIEW IF EXISTS {qname} CASCADE",
        f"CREATE MATERIALIZED VIEW {qname} AS {plan['select_sql']} WITH NO DATA",
        f"CREATE UNIQUE INDEX {quote_identifier(_index_name(model, 'pk_uidx'))} ON {qname} ({pk_cols})",
    ]
    for col in plan["secondary_columns"]:
        stmts.append(
            f"CREATE INDEX {quote_identifier(_index_name(model, col + '_idx'))} "
            f"ON {qname} ({quote_identifier(col)})"
        )
    # first populate is non-concurrent (the view starts WITH NO DATA); later refreshes go CONCURRENTLY.
    stmts.append(f"REFRESH MATERIALIZED VIEW {qname}")
    return stmts


def _autocommit_run(db: Session, statements: list[str]) -> None:
    """Run DDL/refresh on a dedicated AUTOCOMMIT connection (REFRESH CONCURRENTLY forbids a tx block)."""
    engine = db.get_bind()
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        for stmt in statements:
            conn.execute(text(stmt))


def _matview_exists(db: Session, model: DataModel) -> bool:
    row = db.execute(
        text("SELECT 1 FROM pg_matviews WHERE schemaname = :s AND matviewname = :m"),
        {"s": MATVIEW_SCHEMA, "m": model.name},
    ).first()
    return row is not None


def _count_rows(db: Session, model: DataModel) -> int:
    # Count on a fresh connection (not the ORM session's transaction) so it always sees the
    # just-committed matview regardless of the session's snapshot.
    qname = matview_qualified_name(model)
    engine = db.get_bind()
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {qname}")).scalar_one())


def _record_metadata(
    db: Session,
    model: DataModel,
    *,
    duration_sec: float | None,
    row_count: int | None,
    error: str | None,
) -> None:
    model.matview_refresh_duration_sec = duration_sec
    model.matview_row_count = row_count
    model.matview_last_error = error
    if error is None:
        model.matview_last_refresh_at = datetime.now(timezone.utc)
    db.add(model)
    db.commit()
    db.refresh(model)


def _clear_metadata(db: Session, model: DataModel) -> None:
    """Reset all matview metadata (used when the matview is dropped / disabled)."""
    model.matview_refresh_duration_sec = None
    model.matview_row_count = None
    model.matview_last_error = None
    model.matview_last_refresh_at = None
    db.add(model)
    db.commit()
    db.refresh(model)


def _drop_matview_named(db: Session, name: str) -> None:
    """Drop ``mdp_models."<name>"`` (validated identifier) on an autocommit connection. Used both for
    the model's own matview and for cleaning up a renamed model's old-named matview (no orphan)."""
    validate_identifier(name, "Data model name")
    qname = f"{quote_identifier(MATVIEW_SCHEMA)}.{quote_identifier(name)}"
    _autocommit_run(db, [f"DROP MATERIALIZED VIEW IF EXISTS {qname} CASCADE"])


def matview_available(db: Session, model: DataModel) -> bool:
    """True only when the model's matview should AND does exist (matview mode + Type B + Postgres +
    the matview is actually built). The outbound read path gates on this so an enabled-but-not-yet-built
    or failed-build model transparently falls back to the live read-through (never 500s)."""
    return (
        bool(model.matview_enabled)
        and model.type == "B"
        and is_postgres(db)
        and _matview_exists(db, model)
    )


def enable_matview(db: Session, model: DataModel) -> dict[str, Any]:
    """(Re)build the matview from the current model plan + populate it. Idempotent: drops first, so
    it doubles as the rebuild path when the model definition changes. Any failure (invalid mapping,
    non-unique join, DDL error) is recorded into matview_last_error and re-raised as MatviewError."""
    if not is_postgres(db):
        raise MatviewError("Materialized views require PostgreSQL.", status_code=400)
    try:
        plan = build_matview_plan(db, model)
        started = time.perf_counter()
        _autocommit_run(db, _create_matview_ddl(model, plan))
        duration = time.perf_counter() - started
        row_count = _count_rows(db, model)
    except MatviewError as exc:
        _record_metadata(db, model, duration_sec=None, row_count=None, error=exc.message)
        raise
    except Exception as exc:
        _record_metadata(db, model, duration_sec=None, row_count=None, error=str(exc))
        raise MatviewError(f"Matview build failed: {exc}", status_code=400) from exc
    _record_metadata(db, model, duration_sec=duration, row_count=row_count, error=None)
    return {"duration_sec": duration, "row_count": row_count, "rebuilt": True}


def refresh_matview(db: Session, model: DataModel) -> dict[str, Any]:
    """Refresh an existing matview with ``REFRESH ... CONCURRENTLY`` (readers never block). If the
    matview does not exist yet (first call) it is built + populated instead. Failures are recorded into
    matview_last_error and re-raised as MatviewError."""
    if not is_postgres(db):
        raise MatviewError("Materialized views require PostgreSQL.", status_code=400)
    if model.type != "B":
        raise MatviewError("Materialized views are only supported for Type B models.")
    if not _matview_exists(db, model):
        return enable_matview(db, model)
    qname = matview_qualified_name(model)
    try:
        started = time.perf_counter()
        _autocommit_run(db, [f"REFRESH MATERIALIZED VIEW CONCURRENTLY {qname}"])
        duration = time.perf_counter() - started
        row_count = _count_rows(db, model)
    except Exception as exc:
        _record_metadata(db, model, duration_sec=None, row_count=None, error=str(exc))
        raise MatviewError(f"Matview refresh failed: {exc}", status_code=400) from exc
    _record_metadata(db, model, duration_sec=duration, row_count=row_count, error=None)
    return {"duration_sec": duration, "row_count": row_count, "rebuilt": False}


def drop_matview(db: Session, model: DataModel) -> None:
    """Drop the matview (matview mode off, or the model is deleted). Source data is untouched. No-op on
    non-Postgres dialects."""
    if not is_postgres(db):
        return
    _drop_matview_named(db, model.name)
    _clear_metadata(db, model)


def apply_matview_on_save(
    db: Session, model: DataModel, *, previously_enabled: bool, previous_name: str | None = None
) -> None:
    """Reconcile the matview after a model create/edit. "Definition change = rebuild": when the model
    should have a matview (enabled + Type B + Postgres) it is rebuilt from the latest attributes/joins;
    otherwise (disabled, or type flipped away from B) the matview is dropped. On a RENAME the old-named
    matview is also dropped so mdp_models is left with no orphan (M5). Both the drop and the build are
    guarded: a reconcile failure is recorded into matview_last_error and never turns a committed model
    save into a 500 (the model row is already committed)."""
    if not is_postgres(db):
        return
    previous_name = previous_name or model.name
    should_have = bool(model.matview_enabled) and model.type == "B"
    name_changed = previous_name != model.name

    # 1) Clean up the OLD matview when the model no longer wants one, OR it was renamed (else the
    #    old-named matview lingers as an orphan). Guarded so a DDL/lock error can't fail the save.
    if previously_enabled and (not should_have or name_changed):
        try:
            _drop_matview_named(db, previous_name)
        except Exception as exc:
            _record_metadata(
                db, model, duration_sec=None, row_count=None, error=f"old matview drop failed: {exc}"
            )
        else:
            if not should_have:
                _clear_metadata(db, model)

    # 2) (Re)build under the current name when the model should have a matview.
    if should_have:
        try:
            enable_matview(db, model)
        except MatviewError:
            pass  # already recorded into matview_last_error by enable_matview
        except Exception as exc:  # pragma: no cover - defensive
            _record_metadata(db, model, duration_sec=None, row_count=None, error=str(exc))
