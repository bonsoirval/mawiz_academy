"""Ensure referral type has the normal server default.

Revision ID: 94746cea01e1
Revises: 8cd128b3b35b
"""

from alembic import op
import sqlalchemy as sa

revision = "94746cea01e1"
down_revision = "8cd128b3b35b"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "referral" not in inspector.get_table_names():
        raise RuntimeError(
            "Cannot reconcile referral_type: referral table is missing."
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("referral")
    }

    if "referral_type" not in columns:
        op.add_column(
            "referral",
            sa.Column(
                "referral_type",
                sa.String(length=24),
                nullable=False,
                server_default="normal",
            ),
        )
    else:
        op.alter_column(
            "referral",
            "referral_type",
            existing_type=sa.String(length=24),
            server_default="normal",
            existing_nullable=False,
        )


def downgrade():
    raise RuntimeError(
        "Automatic downgrade is disabled for this migration. "
        "Use a reviewed recovery migration instead."
    )
