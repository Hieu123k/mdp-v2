"""add materialized-view fields to data models

Adds the per-model matview toggle + refresh metadata for the Type B Materialized View PoC
(prompt 14). All columns are additive and nullable / default-off, so existing models and the
Type B read-through behaviour are unchanged. down_revision=018 keeps a single alembic head.

Revision ID: 202605300019
Revises: 202605300018
Create Date: 2026-06-14 00:19:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202605300019"
down_revision = "202605300018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_models",
        sa.Column("matview_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "data_models",
        sa.Column("matview_last_refresh_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_models",
        sa.Column("matview_refresh_duration_sec", sa.Float(), nullable=True),
    )
    op.add_column(
        "data_models",
        sa.Column("matview_row_count", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "data_models",
        sa.Column("matview_last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_models", "matview_last_error")
    op.drop_column("data_models", "matview_row_count")
    op.drop_column("data_models", "matview_refresh_duration_sec")
    op.drop_column("data_models", "matview_last_refresh_at")
    op.drop_column("data_models", "matview_enabled")
