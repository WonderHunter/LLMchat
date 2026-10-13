"""consommation et coût des réponses

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cost", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.drop_column("cost")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
