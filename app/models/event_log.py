"""Event log ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventLog(Base):
    """Fact-layer event log."""

    __tablename__ = "event_logs"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('pending', 'success', 'failed', 'fallback', 'degraded')",
            name="ck_event_logs_parse_status",
        ),
        CheckConstraint(
            "processed_status IN ('new', 'compressed', 'archived', 'deleted')",
            name="ck_event_logs_processed_status",
        ),
        UniqueConstraint("source", "external_event_id", name="uq_event_logs_source_external_event_id"),
        UniqueConstraint("source", "payload_hash", name="uq_event_logs_source_payload_hash"),
        Index("idx_event_logs_user_occurred_at", "user_id", "occurred_at"),
        Index("idx_event_logs_user_status", "user_id", "parse_status", "processed_status"),
        Index("idx_event_logs_payload_gin", "raw_payload", postgresql_using="gin"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parsed_impact: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    parse_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    linked_node_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'"),
    )
    processed_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'new'"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    source_sequence: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
