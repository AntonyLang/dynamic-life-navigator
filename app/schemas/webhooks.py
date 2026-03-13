"""Schemas for webhook ingestion APIs."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WebhookIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    accepted: bool
    duplicate: bool
    event_id: UUID


WebhookSource = Literal["strava", "github", "calendar"]


class WebhookPayloadEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    payload: dict[str, Any] | None = None
