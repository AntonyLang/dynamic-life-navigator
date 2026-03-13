"""Schemas for state APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel, UserStateSnapshot


class StateResponse(APIModel):
    request_id: str
    state: UserStateSnapshot


class StateResetRequest(APIModel):
    mental_energy: int = Field(ge=0, le=100)
    physical_energy: int = Field(ge=0, le=100)
    reason: str


class StateResetResponse(APIModel):
    request_id: str
    state: UserStateSnapshot
    reset_reason: str
    updated_at: datetime
