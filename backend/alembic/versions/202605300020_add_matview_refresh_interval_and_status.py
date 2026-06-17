"""add matview auto-refresh interval + last-refresh status to data models

prompt 25 (MatviewRefresher feature): per-model auto-refresh cadence
``matview_refresh_interval_sec`` (NULL/0 = manual only; >0 = the background MatviewRefresher refreshes
the matview every N seconds) and ``matview_last_refresh_status`` ("ok"/"error", surfaced read-only in the
UI). Both additive + nullable, so existing models and the manual-refresh behaviour are unchanged.
down_revision=019 keeps a single alembic head (020).

Revision ID: 202605300020
Revises: 202605300019
Create Date: 2026-06-17 00:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202605300020"
down_revision = "202605300019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_models",
        sa.Column("matview_refresh_interval_sec", sa.Integer(), nullable=True),
    )
    op.add_column(
        "data_models",
        sa.Column("matview_last_refresh_status", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_models", "matview_last_refresh_status")
    op.drop_column("data_models", "matview_refresh_interval_sec")
