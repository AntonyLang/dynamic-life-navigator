"""Prompt and schema assets for the future structured event parser."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.schemas.parsing import CanonicalEventType, CanonicalFocusMode, ParserDecisionDTO

if TYPE_CHECKING:
    from app.models.event_log import EventLog


PROMPT_DIR = Path(__file__).resolve().parent
STRUCTURED_EVENT_PARSER_PROMPT_VERSION = "structured_event_parser_prompt_v1"
STRUCTURED_EVENT_PARSER_SYSTEM_PROMPT_PATH = PROMPT_DIR / "structured_event_parser_system.md"
CANONICAL_EVENT_TYPES: tuple[str, ...] = CanonicalEventType.__args__
CANONICAL_FOCUS_MODES: tuple[str, ...] = CanonicalFocusMode.__args__


@lru_cache(maxsize=1)
def load_structured_event_parser_system_prompt() -> str:
    """Load the system prompt for the structured event parser shell."""

    return STRUCTURED_EVENT_PARSER_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_structured_event_parser_payload_summary(event: EventLog) -> str:
    """Render a compact, transport-safe raw payload summary for model input.

    The parser already receives `raw_text` separately, so when the payload also
    carries an identical top-level `text` field we drop it to avoid duplicated
    multilingual content. We also serialize the payload summary with
    `ensure_ascii=True` so the model still receives valid JSON while the wire
    representation stays ASCII-safe.
    """

    payload = dict(event.raw_payload or {})
    raw_text = event.raw_text or ""
    if raw_text and isinstance(payload.get("text"), str) and payload["text"] == raw_text:
        payload.pop("text")
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def build_structured_event_parser_user_prompt(event: EventLog) -> str:
    """Render a compact user prompt payload for a future model-backed parser."""

    raw_payload = build_structured_event_parser_payload_summary(event)
    return "\n".join(
        [
            "Parse the following event into the response schema.",
            f"allowed_event_types: {', '.join(CANONICAL_EVENT_TYPES)}",
            f"allowed_focus_modes: {', '.join(repr(value) for value in CANONICAL_FOCUS_MODES)}",
            "Map the event to the canonical vocabulary above. Do not invent new event_type or focus_mode values.",
            f"source: {event.source}",
            f"source_event_type: {event.source_event_type or ''}",
            f"occurred_at: {event.occurred_at.isoformat() if event.occurred_at is not None else ''}",
            f"raw_text: {event.raw_text or ''}",
            f"raw_payload_json: {raw_payload}",
        ]
    )


@lru_cache(maxsize=1)
def build_structured_event_parser_response_schema() -> dict[str, Any]:
    """Return the JSON schema for a validated parser decision."""

    return ParserDecisionDTO.model_json_schema()


@lru_cache(maxsize=1)
def build_structured_event_parser_model_response_schema() -> dict[str, Any]:
    """Return a flattened schema for model providers with narrower JSON-schema support.

    This intentionally avoids `$defs`, `$ref`, and nullable unions so Gemini's
    `responseJsonSchema` accepts it more reliably. Provider metadata is injected
    locally after validation, so the model only needs to return status/impact.
    """

    return {
        "type": "object",
        "title": "StructuredEventParserCandidate",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["success", "fallback", "failed"],
            },
            "impact": {
                "type": "object",
                "properties": {
                    "event_summary": {"type": "string"},
                    "event_type": {
                        "type": "string",
                        "enum": list(CANONICAL_EVENT_TYPES),
                    },
                    "mental_delta": {"type": "integer"},
                    "physical_delta": {"type": "integer"},
                    "focus_mode": {
                        "type": "string",
                        "enum": list(CANONICAL_FOCUS_MODES),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "should_offer_pull_hint": {"type": "boolean"},
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
                "required": [
                    "event_summary",
                    "event_type",
                    "mental_delta",
                    "physical_delta",
                    "focus_mode",
                    "tags",
                    "should_offer_pull_hint",
                    "confidence",
                ],
            },
        },
        "required": ["status"],
    }


def build_structured_event_parser_request(event: EventLog, model_name: str) -> dict[str, Any]:
    """Build the complete request artifact set for a structured parser call."""

    return {
        "system_prompt": load_structured_event_parser_system_prompt(),
        "user_prompt": build_structured_event_parser_user_prompt(event),
        "response_schema": build_structured_event_parser_response_schema(),
        "metadata": {
            "prompt_version": STRUCTURED_EVENT_PARSER_PROMPT_VERSION,
            "model_name": model_name,
        },
    }
