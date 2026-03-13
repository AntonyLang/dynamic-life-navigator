"""Common API schema models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base Pydantic model for API schemas."""

    model_config = ConfigDict(from_attributes=True)


class UserStateSnapshot(APIModel):
    mental_energy: int
    physical_energy: int
    focus_mode: str
    do_not_disturb_until: datetime | None = None
    recent_context: str | None = None
    last_updated_at: datetime | None = None


class RecommendationItem(APIModel):
    node_id: UUID
    title: str
    message: str
    reason_tags: list[str]
