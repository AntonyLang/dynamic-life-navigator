"""Internal DTOs for parser and profiling pipelines."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CanonicalEventType = Literal[
    "chat_update",
    "rest",
    "exercise",
    "light_admin",
    "coordination",
    "github",
    "calendar",
    "strava",
    "other",
]

CanonicalFocusMode = Literal[
    "",
    "tired",
    "recovered",
    "light_admin",
    "social",
    "focused",
    "bored",
    "commuting",
    "unknown",
]

CanonicalProfileContextTag = Literal[
    "movement",
    "deep_focus",
    "light_admin",
    "social",
]

CanonicalProfileConfidenceLevel = Literal[
    "low",
    "medium",
    "high",
]


class ParserImpactDTO(BaseModel):
    """Validated parser output shape used before state mutation."""

    event_summary: str
    event_type: CanonicalEventType
    mental_delta: int = Field(ge=-100, le=100)
    physical_delta: int = Field(ge=-100, le=100)
    focus_mode: CanonicalFocusMode = ""
    tags: list[str] = Field(default_factory=list)
    should_offer_pull_hint: bool
    confidence: float = Field(ge=0.0, le=1.0)


class ParserMetadataDTO(BaseModel):
    """Internal parse metadata for logging and future provider comparison."""

    provider: str
    parser_version: str
    prompt_version: str | None = None
    model_name: str | None = None
    fallback_reason: str | None = None
    error_detail: str | None = None


class ParserDecisionDTO(BaseModel):
    """Validated parser decision returned by a parser provider."""

    status: Literal["success", "fallback", "failed"]
    impact: ParserImpactDTO | None = None
    metadata: ParserMetadataDTO


class NodeProfileOutputDTO(BaseModel):
    """Validated async profiling output used before writing node fields."""

    mental_energy_required: int = Field(ge=0, le=100)
    physical_energy_required: int = Field(ge=0, le=100)
    estimated_minutes: int = Field(ge=10, le=240)
    recommended_context_tags: list[CanonicalProfileContextTag] = Field(default_factory=list)
    confidence_level: CanonicalProfileConfidenceLevel
    ai_context: dict[str, Any] = Field(default_factory=dict)


class NodeProfileMetadataDTO(BaseModel):
    """Internal profile metadata for comparison and future provider rollout."""

    provider: str
    profile_version: str
    prompt_version: str | None = None
    model_name: str | None = None
    fallback_reason: str | None = None
    error_detail: str | None = None


class NodeProfileDecisionDTO(BaseModel):
    """Validated profiling result wrapper for current deterministic providers."""

    status: Literal["completed", "missing"]
    node_id: str
    profile: NodeProfileOutputDTO | None = None
    metadata: NodeProfileMetadataDTO | None = None
