"""Schemas for recommendation APIs."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, RecommendationItem


class RecommendationPullResponse(APIModel):
    request_id: str
    recommendation_id: UUID
    mode: Literal["pull"]
    items: list[RecommendationItem]
    empty_state: bool
    fallback_message: str | None = None


class RecommendationBriefSummary(APIModel):
    active_projects: int
    active_values: int
    urgent_nodes: int
    stale_nodes: int


class RecommendationBriefItem(APIModel):
    node_id: str
    title: str
    status: str
    health: str
    next_hint: str


class RecommendationBriefResponse(APIModel):
    request_id: str
    summary: RecommendationBriefSummary
    items: list[RecommendationBriefItem]


class RecommendationFeedbackRequest(APIModel):
    feedback: Literal["accepted", "ignored", "dismissed", "rejected", "snoozed"]
    node_id: UUID | None = None
    channel: str | None = None


class RecommendationFeedbackResponse(APIModel):
    request_id: str
    recommendation_id: UUID
    accepted: bool = True
    feedback: str


class RecommendationPullQuery(APIModel):
    limit: int = Field(default=2, ge=1, le=3)
    include_debug: bool = False
