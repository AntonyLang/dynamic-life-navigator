"""Parser-provider boundary for deterministic and future structured parsers."""

from __future__ import annotations

from typing import Protocol

from app.models.event_log import EventLog
from app.schemas.parsing import ParserDecisionDTO
from app.services.signal_catalog import find_first_parser_signal


DETERMINISTIC_PARSER_VERSION = "deterministic_signal_catalog_v1"

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


_DETERMINISTIC_PROVIDER = DeterministicEventParserProvider()


def get_event_parser_provider() -> EventParserProvider:
    """Return the active parser provider.

    Step 1 keeps the runtime behavior unchanged by always returning the
    deterministic provider. Configuration-driven selection comes next.
    """

    return _DETERMINISTIC_PROVIDER
