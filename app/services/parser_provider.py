"""Parser-provider boundary for deterministic and future structured parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError

from app.core.config import get_settings
from app.prompts.structured_event_parser_assets import (
    build_structured_event_parser_request,
)
from app.schemas.parsing import ParserDecisionDTO
from app.services.signal_catalog import find_first_parser_signal

if TYPE_CHECKING:
    from app.models.event_log import EventLog


DETERMINISTIC_PARSER_VERSION = "deterministic_signal_catalog_v1"
STRUCTURED_STUB_PARSER_VERSION = "structured_stub_v0"
STRUCTURED_STUB_PROMPT_VERSION = "structured_stub_prompt_v0"
STRUCTURED_MODEL_SHELL_PARSER_VERSION = "structured_model_shell_v0"

PARSER_SIGNAL_OUTPUTS = {
    "mental_load": {
        "event_type": "chat_update",
        "mental_delta": -20,
        "physical_delta": 0,
        "focus_mode": "tired",
        "tags": ["mental_load"],
        "should_offer_pull_hint": True,
        "confidence": 0.7,
    },
    "recovery": {
        "event_type": "rest",
        "mental_delta": 15,
        "physical_delta": 10,
        "focus_mode": "recovered",
        "tags": ["recovery"],
        "should_offer_pull_hint": False,
        "confidence": 0.7,
    },
    "movement": {
        "event_type": "exercise",
        "mental_delta": 10,
        "physical_delta": -15,
        "focus_mode": "recovered",
        "tags": ["movement", "recovery"],
        "should_offer_pull_hint": True,
        "confidence": 0.7,
    },
    "light_admin": {
        "event_type": "light_admin",
        "mental_delta": -5,
        "physical_delta": -5,
        "focus_mode": "light_admin",
        "tags": ["light_admin"],
        "should_offer_pull_hint": True,
        "confidence": 0.65,
    },
    "coordination": {
        "event_type": "coordination",
        "mental_delta": -10,
        "physical_delta": 0,
        "focus_mode": "social",
        "tags": ["coordination"],
        "should_offer_pull_hint": True,
        "confidence": 0.65,
    },
}


class EventParserProvider(Protocol):
    """Small provider boundary so structured parsing can slot in later."""

    name: str
    parser_version: str

    def parse(self, event: EventLog) -> ParserDecisionDTO:
        """Produce a validated parse decision for a stored event."""


class DeterministicEventParserProvider:
    """Current rule-driven parser provider used by default."""

    name = "deterministic"
    parser_version = DETERMINISTIC_PARSER_VERSION

    def parse(self, event: EventLog) -> ParserDecisionDTO:
        text = (event.raw_text or "").strip()
        summary = text[:300] if text else f"{event.source} event received"

        if not text and not event.raw_payload:
            return ParserDecisionDTO(
                status="failed",
                impact=None,
                metadata={
                    "provider": self.name,
                    "parser_version": self.parser_version,
                    "fallback_reason": "empty_event",
                },
            )

        signal_match = find_first_parser_signal(text)
        if signal_match is not None:
            return ParserDecisionDTO(
                status="success",
                impact={
                    "event_summary": summary,
                    **PARSER_SIGNAL_OUTPUTS[signal_match.signal_name],
                },
                metadata={
                    "provider": self.name,
                    "parser_version": self.parser_version,
                },
            )

        if event.source in {"github", "calendar", "strava"}:
            return ParserDecisionDTO(
                status="fallback",
                impact={
                    "event_summary": summary,
                    "event_type": event.source,
                    "mental_delta": 0,
                    "physical_delta": 0,
                    "focus_mode": "",
                    "tags": [event.source],
                    "should_offer_pull_hint": False,
                    "confidence": 0.45,
                },
                metadata={
                    "provider": self.name,
                    "parser_version": self.parser_version,
                    "fallback_reason": "source_passthrough",
                },
            )

        return ParserDecisionDTO(
            status="fallback",
            impact={
                "event_summary": summary,
                "event_type": "other",
                "mental_delta": 0,
                "physical_delta": 0,
                "focus_mode": "",
                "tags": [],
                "should_offer_pull_hint": False,
                "confidence": 0.3,
            },
            metadata={
                "provider": self.name,
                "parser_version": self.parser_version,
                "fallback_reason": "unmatched_text",
            },
        )


class StructuredStubEventParserProvider:
    """No-op structured parser stub that delegates to deterministic parsing.

    This keeps runtime behavior stable while proving out provider selection
    and structured metadata wiring before any model-backed parser exists.
    """

    name = "structured_stub"
    parser_version = STRUCTURED_STUB_PARSER_VERSION
    prompt_version = STRUCTURED_STUB_PROMPT_VERSION
    model_name = "stub"

    def __init__(self, fallback_provider: EventParserProvider | None = None) -> None:
        self._fallback_provider = fallback_provider or DeterministicEventParserProvider()

    def _build_candidate_payload(self, event: EventLog, attempt: int) -> dict[str, object]:
        delegated = self._fallback_provider.parse(event)
        return {
            "status": delegated.status,
            "impact": delegated.impact.model_dump(mode="json") if delegated.impact is not None else None,
            "metadata": {
                "provider": self.name,
                "parser_version": self.parser_version,
                "prompt_version": self.prompt_version,
                "model_name": self.model_name,
                "fallback_reason": delegated.metadata.fallback_reason,
            },
        }

    def parse(self, event: EventLog) -> ParserDecisionDTO:
        settings = get_settings()
        max_attempts = settings.structured_parser_validation_retries + 1

        for attempt in range(1, max_attempts + 1):
            candidate_payload = self._build_candidate_payload(event, attempt)
            try:
                return ParserDecisionDTO.model_validate(candidate_payload)
            except ValidationError:
                continue

        delegated = self._fallback_provider.parse(event)
        return ParserDecisionDTO(
            status=delegated.status,
            impact=delegated.impact,
            metadata={
                "provider": self.name,
                "parser_version": self.parser_version,
                "prompt_version": self.prompt_version,
                "model_name": self.model_name,
                "fallback_reason": f"validation_error_fallback_after_{max_attempts}_attempts",
            },
        )


class StructuredModelShellEventParserProvider:
    """Model-backed parser shell without a live model call yet.

    This provider builds prompt/schema request artifacts and keeps the
    structured-parser control surface stable, while safely falling back to the
    deterministic provider until model integration is added.
    """

    name = "structured_model_shell"
    parser_version = STRUCTURED_MODEL_SHELL_PARSER_VERSION

    def __init__(self, fallback_provider: EventParserProvider | None = None, model_name: str | None = None) -> None:
        self._fallback_provider = fallback_provider or DeterministicEventParserProvider()
        self._model_name = model_name or "unconfigured-structured-parser"

    def build_request_artifacts(self, event: EventLog) -> dict[str, object]:
        return build_structured_event_parser_request(event, self._model_name)

    def _generate_candidate_payload(self, request_artifacts: dict[str, object], attempt: int) -> dict[str, object] | None:
        return None

    def parse(self, event: EventLog) -> ParserDecisionDTO:
        settings = get_settings()
        request_artifacts = self.build_request_artifacts(event)
        max_attempts = settings.structured_parser_validation_retries + 1

        for attempt in range(1, max_attempts + 1):
            candidate_payload = self._generate_candidate_payload(request_artifacts, attempt)
            if candidate_payload is None:
                break
            try:
                return ParserDecisionDTO.model_validate(candidate_payload)
            except ValidationError:
                continue

        delegated = self._fallback_provider.parse(event)
        return ParserDecisionDTO(
            status=delegated.status,
            impact=delegated.impact,
            metadata={
                "provider": self.name,
                "parser_version": self.parser_version,
                "prompt_version": str(request_artifacts["metadata"]["prompt_version"]),
                "model_name": str(request_artifacts["metadata"]["model_name"]),
                "fallback_reason": "model_call_not_implemented",
            },
        )


_DETERMINISTIC_PROVIDER = DeterministicEventParserProvider()
_STRUCTURED_STUB_PROVIDER = StructuredStubEventParserProvider(_DETERMINISTIC_PROVIDER)


def get_event_parser_provider() -> EventParserProvider:
    """Return the active parser provider.

    Structured selection is intentionally small here: deterministic remains
    the default, and the structured stub delegates back to deterministic so
    behavior stays stable until a validated LLM-backed parser exists.
    """

    settings = get_settings()
    if settings.parser_provider == "structured_stub":
        return _STRUCTURED_STUB_PROVIDER
    if settings.parser_provider == "structured_model_shell":
        return StructuredModelShellEventParserProvider(
            _DETERMINISTIC_PROVIDER,
            model_name=settings.structured_parser_model_name,
        )
    if settings.parser_provider == "openai_responses":
        from app.services.openai_responses_parser import OpenAIResponsesEventParserProvider

        return OpenAIResponsesEventParserProvider(
            _DETERMINISTIC_PROVIDER,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=settings.structured_parser_model_name,
            timeout_seconds=settings.structured_parser_timeout_seconds,
        )
    if settings.parser_provider == "gemini_direct":
        from app.services.gemini_direct_parser import GeminiDirectEventParserProvider

        return GeminiDirectEventParserProvider(
            _DETERMINISTIC_PROVIDER,
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model_name=settings.structured_parser_model_name,
            timeout_seconds=settings.structured_parser_timeout_seconds,
        )
    return _DETERMINISTIC_PROVIDER
