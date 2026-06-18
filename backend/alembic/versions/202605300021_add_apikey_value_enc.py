"""store the API-key value encrypted-at-rest so it can be re-viewed (prompt 28, option ii)

Adds two nullable columns to ``api_keys``:
- ``key_value_enc`` (Text): the Fernet-encrypted key value, written at creation time when APIKEY_ENC_KEY
  is configured, so the plaintext can be re-revealed behind the level-2 password. NULL for keys created
  before this feature (hash-only → not re-viewable) and when the reveal feature is off.
- ``key_enc_ver`` (Integer): the encryption-scheme version marker, for future key rotation.

Both additive + nullable, so existing keys and hash-based authentication are unchanged.
down_revision=020 keeps a single alembic head (021).

Revision ID: 202605300021
Revises: 202605300020
Create Date: 2026-06-18 00:21:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202605300021"
down_revision = "202605300020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("key_value_enc", sa.Text(), nullable=True))
    op.add_column("api_keys", sa.Column("key_enc_ver", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "key_enc_ver")
    op.drop_column("api_keys", "key_value_enc")
