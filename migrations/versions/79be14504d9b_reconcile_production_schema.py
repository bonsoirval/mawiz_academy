
"""Reconcile production schema.

Revision ID: 79be14504d9b
Revises: 94746cea01e1

This migration adds the six missing program/campaign tables and
reconciles the referral and track tables without recreating existing data.
"""

from alembic import op
import sqlalchemy as sa


revision = "79be14504d9b"
down_revision = "94746cea01e1"
branch_labels = None
depends_on = None


NEW_TABLES = {
    "mgsc_campaign",
    "mgsc_event",
    "program_enrollment",
    "program_payment",
    "program_referral_event",
    "share_ledger_entry",
}



def _check_schema():
    """Validate whether this is a fresh or unreconciled production schema."""

    conn = op.get_bind()

    if conn.dialect.name != "postgresql":
        raise RuntimeError(
            "This reconciliation migration requires PostgreSQL."
        )

    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    required_existing = {"user", "track", "referral"}
    missing_existing = required_existing - tables

    if missing_existing:
        raise RuntimeError(
            f"Required tables are missing: {sorted(missing_existing)}"
        )

    expected_missing_columns = {
        "track": {"price_amount", "price_currency"},
        "referral": {
            "share_percent",
            "label",
            "starts_at",
            "ends_at",
        },
    }

    missing_columns = {}

    for table, expected in expected_missing_columns.items():
        existing = {
            column["name"]
            for column in inspector.get_columns(table)
        }
        missing_columns[table] = expected - existing

    referral_columns = {
        column["name"]
        for column in inspector.get_columns('referral')
    }

    referral_indexes = {
        index['name']
        for index in inspector.get_indexes('referral')
    }

    if 'referral_type' not in referral_columns:
        raise RuntimeError(
            "Required referral_type column is missing."
        )

    existing_new_tables = NEW_TABLES & tables

    # Fresh installation: all target tables and columns already exist.
    if NEW_TABLES.issubset(tables) and not any(missing_columns.values()):
        return True

    # Existing production baseline: all six tables and target columns
    # are absent, as confirmed by the earlier schema audit.
    if (
        not existing_new_tables
        and all(
            missing_columns[table] == expected
            for table, expected in expected_missing_columns.items()
        )
        and "ix_referral_referral_type" not in referral_indexes
    ):
        return False

    raise RuntimeError(
        "Partial schema detected. Automatic reconciliation stopped. "
        f"Existing target tables: {sorted(existing_new_tables)}; "
        f"missing columns: {missing_columns}"
    )


def upgrade():
    if _check_schema():
        return

    # ---------------------------------------------------------
    # 1. Reconcile existing track table
    # ---------------------------------------------------------
    op.add_column(
        'track',
        sa.Column(
            'price_amount',
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0"
        )
    )
    op.add_column(
        "track",
        sa.Column(
            "price_currency",
            sa.String(3),
            nullable=False,
            server_default="NGN",
        ),
    )



    # ---------------------------------------------------------
    # 2. Reconcile existing referral table
    # ---------------------------------------------------------


    # Add nullable first, backfill existing records, then enforce NOT NULL.
    op.add_column(
        "referral",
        sa.Column(
            "share_percent",
            sa.Numeric(5, 2),
            nullable=True,
        ),
    )

    op.execute(
        sa.text(
            "UPDATE referral "
            "SET share_percent = 10.00 "
            "WHERE share_percent IS NULL"
        )
    )

    op.alter_column(
        "referral",
        "share_percent",
        existing_type=sa.Numeric(5, 2),
        nullable=False,
    )

    op.add_column(
        "referral",
        sa.Column(
            "label",
            sa.String(180),
            nullable=True,
            server_default=sa.text("''"),
        ),
    )

    op.add_column(
        "referral",
        sa.Column("starts_at", sa.DateTime(), nullable=True),
    )

    op.add_column(
        "referral",
        sa.Column("ends_at", sa.DateTime(), nullable=True),
    )

    op.create_index(
        "ix_referral_referral_type",
        "referral",
        ["referral_type"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 3. Create program_payment
    # ---------------------------------------------------------

    op.create_table(
        "program_payment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(80), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("provider_fee_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("eligible_revenue_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("paystack_transaction_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["track_id"], ["track.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_program_payment_reference",
        "program_payment",
        ["reference"],
        unique=True,
    )
    op.create_index(
        "ix_program_payment_status",
        "program_payment",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_program_payment_track_id",
        "program_payment",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_program_payment_user_id",
        "program_payment",
        ["user_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 4. Create mgsc_campaign
    # ---------------------------------------------------------

    op.create_table(
        "mgsc_campaign",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("beneficiary_user_id", sa.Integer(), nullable=True),
        sa.Column("beneficiary_name", sa.String(180), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("min_signups", sa.Integer(), nullable=False),
        sa.Column("max_signups", sa.Integer(), nullable=False),
        sa.Column("min_program_purchases", sa.Integer(), nullable=False),
        sa.Column("max_program_purchases", sa.Integer(), nullable=False),
        sa.Column("share_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("revenue_basis", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("eligible_at", sa.DateTime(), nullable=True),
        sa.Column("eligible_signup_count", sa.Integer(), nullable=False),
        sa.Column("eligible_purchase_count", sa.Integer(), nullable=False),
        sa.Column("estimated_share_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("accrued_share_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["beneficiary_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_mgsc_campaign_beneficiary_user_id",
        "mgsc_campaign",
        ["beneficiary_user_id"],
    )
    op.create_index(
        "ix_mgsc_campaign_ends_at",
        "mgsc_campaign",
        ["ends_at"],
    )
    op.create_index(
        "ix_mgsc_campaign_starts_at",
        "mgsc_campaign",
        ["starts_at"],
    )
    op.create_index(
        "ix_mgsc_campaign_status",
        "mgsc_campaign",
        ["status"],
    )

    # ---------------------------------------------------------
    # 5. Create mgsc_event
    # ---------------------------------------------------------

    op.create_table(
        "mgsc_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("program_payment_id", sa.Integer(), nullable=True),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["mgsc_campaign.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["program_payment_id"],
            ["program_payment.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )

    op.create_index("ix_mgsc_event_campaign_id", "mgsc_event", ["campaign_id"])
    op.create_index("ix_mgsc_event_event_type", "mgsc_event", ["event_type"])
    op.create_index("ix_mgsc_event_occurred_at", "mgsc_event", ["occurred_at"])
    op.create_index(
        "ix_mgsc_event_program_payment_id",
        "mgsc_event",
        ["program_payment_id"],
    )
    op.create_index("ix_mgsc_event_user_id", "mgsc_event", ["user_id"])

    # ---------------------------------------------------------
    # 6. Create program_enrollment
    # ---------------------------------------------------------

    op.create_table(
        "program_enrollment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("purchased_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["program_payment.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["track.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
        sa.UniqueConstraint(
            "user_id",
            "track_id",
            name="uq_program_enrollment_user_track",
        ),
    )

    op.create_index(
        "ix_program_enrollment_status",
        "program_enrollment",
        ["status"],
    )
    op.create_index(
        "ix_program_enrollment_track_id",
        "program_enrollment",
        ["track_id"],
    )
    op.create_index(
        "ix_program_enrollment_user_id",
        "program_enrollment",
        ["user_id"],
    )

    # ---------------------------------------------------------
    # 7. Create program_referral_event
    # ---------------------------------------------------------

    op.create_table(
        "program_referral_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=True),
        sa.Column("program_payment_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["program_payment_id"],
            ["program_payment.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["referral_id"], ["referral.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["referred_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_program_referral_event_event_type",
        "program_referral_event",
        ["event_type"],
    )
    op.create_index(
        "ix_program_referral_event_program_payment_id",
        "program_referral_event",
        ["program_payment_id"],
        unique=True,
    )
    op.create_index(
        "ix_program_referral_event_referral_id",
        "program_referral_event",
        ["referral_id"],
    )
    op.create_index(
        "ix_program_referral_event_referred_user_id",
        "program_referral_event",
        ["referred_user_id"],
    )
    op.create_index(
        "ix_program_referral_event_status",
        "program_referral_event",
        ["status"],
    )

    # ---------------------------------------------------------
    # 8. Create share_ledger_entry
    # ---------------------------------------------------------

    op.create_table(
        "share_ledger_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("basis_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("share_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["mgsc_campaign.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_share_ledger_entry_campaign_id",
        "share_ledger_entry",
        ["campaign_id"],
    )
    op.create_index(
        "ix_share_ledger_entry_status",
        "share_ledger_entry",
        ["status"],
    )


def downgrade():
    raise RuntimeError(
        "Automatic downgrade is intentionally disabled for this production "
        "reconciliation migration. Dropping these tables or columns could "
        "destroy production data. Use a reviewed recovery migration instead."
    )
