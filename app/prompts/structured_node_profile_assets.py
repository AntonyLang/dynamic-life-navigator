"""Prompt and schema assets for structured async node profiling."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.schemas.parsing import (
    CanonicalProfileConfidenceLevel,
    CanonicalProfileContextTag,
    NodeProfileDecisionDTO,
)

if TYPE_CHECKING:
    from app.models.action_node import ActionNode


PROMPT_DIR = Path(__file__).resolve().parent
STRUCTURED_NODE_PROFILE_PROMPT_VERSION = "structured_node_profile_prompt_v2"
STRUCTURED_NODE_PROFILE_SYSTEM_PROMPT_PATH = PROMPT_DIR / "structured_node_profile_system.md"
CANONICAL_PROFILE_CONTEXT_TAGS: tuple[str, ...] = CanonicalProfileContextTag.__args__
CANONICAL_PROFILE_CONFIDENCE_LEVELS: tuple[str, ...] = CanonicalProfileConfidenceLevel.__args__
CANONICAL_PROFILE_EXAMPLES: tuple[str, ...] = (
    "- organize inbox, cleanup, archive, or 整理归档 -> recommended_context_tags=[light_admin]",
    "- debugging, report writing, research, or 调试写报告 -> recommended_context_tags=[deep_focus]",
    "- walk, run, ride, or exercise -> recommended_context_tags=[movement]",
    "- call, meeting, sync, or 沟通讨论 -> recommended_context_tags=[social]",
)


@lru_cache(maxsize=1)
def load_structured_node_profile_system_prompt() -> str:
    """Load the system prompt for the structured node profiler."""

    return STRUCTURED_NODE_PROFILE_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_structured_node_profile_user_prompt(node: ActionNode) -> str:
    """Render a compact user prompt payload for a model-backed node profiler."""

    tags_json = json.dumps(node.tags or [], ensure_ascii=True)
    return "\n".join(
        [
            "Profile the following action node into the response schema.",
            f"allowed_context_tags: {', '.join(CANONICAL_PROFILE_CONTEXT_TAGS)}",
            f"allowed_confidence_levels: {', '.join(CANONICAL_PROFILE_CONFIDENCE_LEVELS)}",
            "Map the node to the canonical vocabulary above. Do not invent new context tags or confidence levels.",
            "Canonical examples:",
            *CANONICAL_PROFILE_EXAMPLES,
            f"title: {node.title}",
            f"summary: {node.summary or ''}",
            f"tags_json: {tags_json}",
            f"drive_type: {node.drive_type}",
        ]
    )


@lru_cache(maxsize=1)
def build_structured_node_profile_response_schema() -> dict[str, Any]:
    """Return the JSON schema for a validated node profile decision."""

    return NodeProfileDecisionDTO.model_json_schema()


@lru_cache(maxsize=1)
def build_structured_node_profile_model_response_schema() -> dict[str, Any]:
    """Return a flattened schema for model providers with narrower JSON-schema support."""

    return {
        "type": "object",
        "title": "StructuredNodeProfileCandidate",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["completed"],
            },
            "profile": {
                "type": "object",
                "properties": {
                    "mental_energy_required": {"type": "integer", "minimum": 0, "maximum": 100},
                    "physical_energy_required": {"type": "integer", "minimum": 0, "maximum": 100},
                    "estimated_minutes": {"type": "integer", "minimum": 10, "maximum": 240},
                    "recommended_context_tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(CANONICAL_PROFILE_CONTEXT_TAGS),
                        },
                    },
                    "confidence_level": {
                        "type": "string",
                        "enum": list(CANONICAL_PROFILE_CONFIDENCE_LEVELS),
                    },
                },
                "required": [
                    "mental_energy_required",
                    "physical_energy_required",
                    "estimated_minutes",
                    "recommended_context_tags",
                    "confidence_level",
                ],
            },
        },
        "required": ["status", "profile"],
    }


def build_structured_node_profile_request(node: ActionNode, model_name: str) -> dict[str, Any]:
    """Build the complete request artifact set for a structured node profile call."""

    return {
        "system_prompt": load_structured_node_profile_system_prompt(),
        "user_prompt": build_structured_node_profile_user_prompt(node),
        "response_schema": build_structured_node_profile_response_schema(),
        "metadata": {
            "prompt_version": STRUCTURED_NODE_PROFILE_PROMPT_VERSION,
            "model_name": model_name,
        },
    }
