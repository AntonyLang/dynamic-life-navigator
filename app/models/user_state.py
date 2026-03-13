"""User state ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserState(Base):
    """Snapshot-layer current user state."""

    __tablename__ = "user_state"
    __table_args__ = (
        CheckConstraint("mental_energy BETWEEN 0 AND 100", name="ck_user_state_mental_energy"),
        CheckConstraint("physical_energy BETWEEN 0 AND 100", name="ck_user_state_physical_energy"),
    )

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    mental_energy: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    physical_energy: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    focus_mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'unknown'"))
    do_not_disturb_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recent_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_last_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
