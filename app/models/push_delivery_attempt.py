"""Push delivery attempt audit ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushDeliveryAttempt(Base):
    """Audit row for each outbound push delivery attempt."""

    __tablename__ = "push_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('webhook_sink')",
            name="ck_push_delivery_attempts_channel",
        ),
        CheckConstraint(
            "delivery_status IN ('sent', 'failed', 'skipped')",
            name="ck_push_delivery_attempts_delivery_status",
        ),
        Index("idx_push_delivery_attempts_recommendation", "recommendation_id"),
        Index("idx_push_delivery_attempts_created_at", "created_at"),
    )

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_records.recommendation_id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    target_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
