"""initial core tables"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260313_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "user_state",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("state_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("mental_energy", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("physical_energy", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("focus_mode", sa.String(length=32), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("do_not_disturb_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recent_context", sa.Text(), nullable=True),
        sa.Column("source_last_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("mental_energy BETWEEN 0 AND 100", name="ck_user_state_mental_energy"),
        sa.CheckConstraint("physical_energy BETWEEN 0 AND 100", name="ck_user_state_physical_energy"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "state_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("change_reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_state_history_user_created_at", "state_history", ["user_id", "created_at"], unique=False)

    op.create_table(
        "action_nodes",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("drive_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("priority_score", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("dynamic_urgency_score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("mental_energy_required", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("physical_energy_required", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("ddl_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_hours", sa.Integer(), server_default=sa.text("12"), nullable=False),
        sa.Column("last_recommended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recommended_context_tags", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("confidence_level", sa.String(length=20), server_default=sa.text("'low'"), nullable=False),
        sa.Column("profiling_status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("profiled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_context", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("drive_type IN ('project', 'value')", name="ck_action_nodes_drive_type"),
        sa.CheckConstraint("status IN ('active', 'paused', 'archived', 'done')", name="ck_action_nodes_status"),
        sa.CheckConstraint("priority_score BETWEEN 0 AND 100", name="ck_action_nodes_priority_score"),
        sa.CheckConstraint("dynamic_urgency_score BETWEEN 0 AND 100", name="ck_action_nodes_dynamic_urgency_score"),
        sa.CheckConstraint("mental_energy_required BETWEEN 0 AND 100", name="ck_action_nodes_mental_energy_required"),
        sa.CheckConstraint("physical_energy_required BETWEEN 0 AND 100", name="ck_action_nodes_physical_energy_required"),
        sa.CheckConstraint("confidence_level IN ('low', 'medium', 'high')", name="ck_action_nodes_confidence_level"),
        sa.CheckConstraint("profiling_status IN ('pending', 'completed', 'failed')", name="ck_action_nodes_profiling_status"),
        sa.PrimaryKeyConstraint("node_id"),
    )
    op.create_index("idx_action_nodes_user_status", "action_nodes", ["user_id", "status"], unique=False)
    op.create_index("idx_action_nodes_user_deadline", "action_nodes", ["user_id", "ddl_timestamp"], unique=False)
    op.create_index("idx_action_nodes_user_energy", "action_nodes", ["user_id", "mental_energy_required", "physical_energy_required"], unique=False)
    op.create_index("idx_action_nodes_tags_gin", "action_nodes", ["tags"], unique=False, postgresql_using="gin")
    op.create_index("idx_action_nodes_ai_context_gin", "action_nodes", ["ai_context"], unique=False, postgresql_using="gin")

    op.create_table(
        "node_annotations",
        sa.Column("annotation_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("annotation_type", sa.String(length=32), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("freshness_score", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_status", sa.String(length=20), server_default=sa.text("'success'"), nullable=False),
        sa.CheckConstraint("freshness_score BETWEEN 0 AND 100", name="ck_node_annotations_freshness_score"),
        sa.CheckConstraint("fetch_status IN ('success', 'failed', 'expired')", name="ck_node_annotations_fetch_status"),
        sa.ForeignKeyConstraint(["node_id"], ["action_nodes.node_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("annotation_id"),
    )
    op.create_index("idx_node_annotations_node_expires", "node_annotations", ["node_id", "expires_at"], unique=False)

    op.create_table(
        "event_logs",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_event_type", sa.String(length=50), nullable=True),
        sa.Column("external_event_id", sa.String(length=128), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parsed_impact", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("parse_status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("linked_node_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("processed_status", sa.String(length=20), server_default=sa.text("'new'"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("source_sequence", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("parse_status IN ('pending', 'success', 'failed', 'fallback', 'degraded')", name="ck_event_logs_parse_status"),
        sa.CheckConstraint("processed_status IN ('new', 'compressed', 'archived', 'deleted')", name="ck_event_logs_processed_status"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("source", "external_event_id", name="uq_event_logs_source_external_event_id"),
        sa.UniqueConstraint("source", "payload_hash", name="uq_event_logs_source_payload_hash"),
    )
    op.create_index("idx_event_logs_user_occurred_at", "event_logs", ["user_id", "occurred_at"], unique=False)
    op.create_index("idx_event_logs_user_status", "event_logs", ["user_id", "parse_status", "processed_status"], unique=False)
    op.create_index("idx_event_logs_payload_gin", "event_logs", ["raw_payload"], unique=False, postgresql_using="gin")

    op.create_table(
        "recommendation_records",
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=False),
        sa.Column("trigger_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_node_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("selected_node_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("ranking_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("rendered_content", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("delivery_status", sa.String(length=20), server_default=sa.text("'generated'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("mode IN ('pull', 'push')", name="ck_recommendation_records_mode"),
        sa.CheckConstraint("delivery_status IN ('generated', 'sent', 'failed', 'skipped')", name="ck_recommendation_records_delivery_status"),
        sa.ForeignKeyConstraint(["trigger_event_id"], ["event_logs.event_id"]),
        sa.PrimaryKeyConstraint("recommendation_id"),
    )
    op.create_index("idx_recommendation_records_user_created_at", "recommendation_records", ["user_id", "created_at"], unique=False)

    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("feedback IN ('accepted', 'ignored', 'dismissed', 'rejected', 'snoozed')", name="ck_recommendation_feedback_feedback"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendation_records.recommendation_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_recommendation_feedback_rec", "recommendation_feedback", ["recommendation_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_recommendation_feedback_rec", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
    op.drop_index("idx_recommendation_records_user_created_at", table_name="recommendation_records")
    op.drop_table("recommendation_records")
    op.drop_index("idx_event_logs_payload_gin", table_name="event_logs", postgresql_using="gin")
    op.drop_index("idx_event_logs_user_status", table_name="event_logs")
    op.drop_index("idx_event_logs_user_occurred_at", table_name="event_logs")
    op.drop_table("event_logs")
    op.drop_index("idx_node_annotations_node_expires", table_name="node_annotations")
    op.drop_table("node_annotations")
    op.drop_index("idx_action_nodes_ai_context_gin", table_name="action_nodes", postgresql_using="gin")
    op.drop_index("idx_action_nodes_tags_gin", table_name="action_nodes", postgresql_using="gin")
    op.drop_index("idx_action_nodes_user_energy", table_name="action_nodes")
    op.drop_index("idx_action_nodes_user_deadline", table_name="action_nodes")
    op.drop_index("idx_action_nodes_user_status", table_name="action_nodes")
    op.drop_table("action_nodes")
    op.drop_index("idx_state_history_user_created_at", table_name="state_history")
    op.drop_table("state_history")
    op.drop_table("user_state")
