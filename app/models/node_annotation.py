"""Node annotation ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NodeAnnotation(Base):
    """Freshness-bounded annotation for action nodes."""

    __tablename__ = "node_annotations"
    __table_args__ = (
        CheckConstraint("freshness_score BETWEEN 0 AND 100", name="ck_node_annotations_freshness_score"),
        CheckConstraint(
            "fetch_status IN ('success', 'failed', 'expired')",
            name="ck_node_annotations_fetch_status",
        ),
        Index("idx_node_annotations_node_expires", "node_id", "expires_at"),
    )

    annotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("action_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    annotation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    freshness_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'success'"))
