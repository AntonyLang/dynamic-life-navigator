"""add push delivery attempts"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260314_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_delivery_attempts",
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), nullable=False),
        sa.Column("target_ref", sa.String(length=500), nullable=True),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("channel IN ('webhook_sink')", name="ck_push_delivery_attempts_channel"),
        sa.CheckConstraint(
            "delivery_status IN ('sent', 'failed', 'skipped')",
            name="ck_push_delivery_attempts_delivery_status",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendation_records.recommendation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "idx_push_delivery_attempts_recommendation",
        "push_delivery_attempts",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        "idx_push_delivery_attempts_created_at",
        "push_delivery_attempts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_push_delivery_attempts_created_at", table_name="push_delivery_attempts")
    op.drop_index("idx_push_delivery_attempts_recommendation", table_name="push_delivery_attempts")
    op.drop_table("push_delivery_attempts")
