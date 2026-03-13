"""Schemas for action node APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class ActionNodeCreateRequest(APIModel):
    drive_type: Literal["project", "value"]
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    priority_score: int | None = Field(default=None, ge=0, le=100)
    dynamic_urgency_score: int | None = Field(default=None, ge=0, le=100)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    ddl_timestamp: datetime | None = None


class ActionNodeResponse(APIModel):
    node_id: UUID
    drive_type: str
    status: str
    title: str
    summary: str | None = None
    tags: list[str]
    priority_score: int
    dynamic_urgency_score: int
    mental_energy_required: int
    physical_energy_required: int
    estimated_minutes: int | None = None
    recommended_context_tags: list[str]
    confidence_level: str
    profiling_status: str
    profiled_at: datetime | None = None


class ActionNodeCreateResponse(APIModel):
    request_id: str
    accepted: bool = True
    profiling_enqueued: bool
    node: ActionNodeResponse
