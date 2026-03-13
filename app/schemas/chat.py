"""Schemas for chat ingestion APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, UserStateSnapshot


class ChatMessageRequest(APIModel):
    channel: str
    message_type: str = Field(default="text")
    text: str
    client_message_id: str
    occurred_at: datetime


class ChatMessageResponse(APIModel):
    request_id: str
    event_id: UUID
    state: UserStateSnapshot
    assistant_reply: str
    suggest_next_action: bool
    accepted: bool = True
    processing: bool = True
