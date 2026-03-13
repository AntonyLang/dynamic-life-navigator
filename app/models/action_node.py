"""Action node ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActionNode(Base):
    """Candidate action node for recommendation selection."""

    __tablename__ = "action_nodes"
    __table_args__ = (
        CheckConstraint("drive_type IN ('project', 'value')", name="ck_action_nodes_drive_type"),
        CheckConstraint("status IN ('active', 'paused', 'archived', 'done')", name="ck_action_nodes_status"),
        CheckConstraint("priority_score BETWEEN 0 AND 100", name="ck_action_nodes_priority_score"),
        CheckConstraint("dynamic_urgency_score BETWEEN 0 AND 100", name="ck_action_nodes_dynamic_urgency_score"),
        CheckConstraint("mental_energy_required BETWEEN 0 AND 100", name="ck_action_nodes_mental_energy_required"),
        CheckConstraint("physical_energy_required BETWEEN 0 AND 100", name="ck_action_nodes_physical_energy_required"),
        CheckConstraint("confidence_level IN ('low', 'medium', 'high')", name="ck_action_nodes_confidence_level"),
        CheckConstraint(
            "profiling_status IN ('pending', 'completed', 'failed')",
            name="ck_action_nodes_profiling_status",
        ),
        Index("idx_action_nodes_user_status", "user_id", "status"),
        Index("idx_action_nodes_user_deadline", "user_id", "ddl_timestamp"),
        Index(
            "idx_action_nodes_user_energy",
            "user_id",
            "mental_energy_required",
            "physical_energy_required",
        ),
        Index("idx_action_nodes_tags_gin", "tags", postgresql_using="gin"),
        Index("idx_action_nodes_ai_context_gin", "ai_context", postgresql_using="gin"),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    drive_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False, server_default=text("'{}'"))
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    dynamic_urgency_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    mental_energy_required: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    physical_energy_required: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ddl_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("12"))
    last_recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recommended_context_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String()),
        nullable=False,
        server_default=text("'{}'"),
    )
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'low'"))
    profiling_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    profiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
