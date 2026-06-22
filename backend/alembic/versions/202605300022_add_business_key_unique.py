"""enforce the business key on Type A generated tables with a UNIQUE index (prompt 36 P0-1 / U1)

Inbound now UPSERTs on ``model.primary_key`` (`INSERT … ON CONFLICT … DO UPDATE`). That requires a physical
UNIQUE constraint on the business-key column(s) — previously the only PK was the surrogate ``id`` UUID, so
re-sending a key appended a duplicate row (Type B JOIN fan-out + matview refresh failures).

For every active Type A model that has a ``primary_key``, this migration:
  1. **de-duplicates "latest wins"** — keeps the row with the greatest (updated_at, created_at, ctid) per
     business key and deletes the rest (so the UNIQUE index can build on a dirty prod DB);
  2. **adds a UNIQUE index** on the business-key column(s). The ``id`` UUID stays the table PRIMARY KEY.
Keyless models (no ``primary_key``) are untouched and stay append-only.

Reversible: downgrade drops the UNIQUE indexes (the de-dup is data and is not restored). Single head 022.

Revision ID: 202605300022
Revises: 202605300021
Create Date: 2026-06-22 00:22:00.000000
"""
import hashlib
import re

from alembic import op
import sqlalchemy as sa


revision = "202605300022"
down_revision = "202605300021"
branch_labels = None
depends_on = None

_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


def _targets(conn):
    rows = conn.execute(sa.text(
        "SELECT name, primary_key, COALESCE(generated_table, 'mdp_data.dm_' || name) AS tbl "
        "FROM public.data_models "
        "WHERE type = 'A' AND COALESCE(primary_key, '') <> ''"
    )).fetchall()
    for name, pk, tbl in rows:
        cols = [c.strip() for c in pk.split(",") if c.strip()]
        yield name, cols, tbl


def _index_name(tbl: str) -> str:
    return "ux_bk_" + hashlib.sha1(tbl.encode("utf-8")).hexdigest()[:16]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return  # sqlite test DB: generated tables are created by fixtures, nothing to migrate

    bad = []
    for name, cols, tbl in _targets(conn):
        schema, bare = tbl.split(".", 1)
        if conn.execute(sa.text("SELECT to_regclass(:t) IS NULL"), {"t": tbl}).scalar():
            continue  # no physical table yet
        present = {r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name=:t"
        ), {"s": schema, "t": bare})}
        for c in cols:
            if not _IDENT.match(c) or c not in present:
                bad.append(f"{name}.{c}")
    if bad:
        # STOP (prompt 36): a configured primary_key that is not a real stored column cannot be UNIQUE-indexed.
        raise RuntimeError(
            "Cannot add business-key UNIQUE: these primary_key columns are not real stored columns: "
            + ", ".join(bad) + ". Fix the model definitions before migrating."
        )

    for name, cols, tbl in _targets(conn):
        schema, bare = tbl.split(".", 1)
        if conn.execute(sa.text("SELECT to_regclass(:t) IS NULL"), {"t": tbl}).scalar():
            continue
        qtbl = f'"{schema}"."{bare}"'
        col_list = ", ".join(f'"{c}"' for c in cols)
        # 1) de-dup, latest wins
        conn.execute(sa.text(
            f"DELETE FROM {qtbl} a USING ("
            f"  SELECT ctid, row_number() OVER ("
            f"    PARTITION BY {col_list}"
            f'    ORDER BY "updated_at" DESC NULLS LAST, "created_at" DESC NULLS LAST, ctid DESC'
            f"  ) AS rn FROM {qtbl}"
            f") b WHERE a.ctid = b.ctid AND b.rn > 1"
        ))
        # 2) UNIQUE index (idempotent)
        conn.execute(sa.text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{_index_name(tbl)}" ON {qtbl} ({col_list})'
        ))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    for _name, _cols, tbl in _targets(conn):
        schema, _bare = tbl.split(".", 1)
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}"."{_index_name(tbl)}"'))
