from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.services.parser_provider import (
    DETERMINISTIC_PARSER_VERSION,
    DeterministicEventParserProvider,
)

settings = get_settings()


def _build_event(*, raw_text: str | None, source: str = "desktop_plugin", raw_payload: dict | None = None) -> EventLog:
    return EventLog(
        event_id=uuid4(),
        user_id=settings.default_user_id,
        source=source,
        source_event_type="text",
        external_event_id=f"test-{uuid4()}",
        payload_hash=f"hash-{uuid4()}",
        raw_text=raw_text,
        raw_payload=raw_payload,
        occurred_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )


def test_deterministic_parser_provider_returns_valid_success_decision():
    provider = DeterministicEventParserProvider()

    decision = provider.parse(
        _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")
    )

    assert decision.status == "success"
    assert decision.impact is not None
    assert decision.impact.event_type == "chat_update"
    assert decision.metadata.provider == "deterministic"
    assert decision.metadata.parser_version == DETERMINISTIC_PARSER_VERSION
    assert decision.metadata.fallback_reason is None


def test_deterministic_parser_provider_returns_fallback_metadata():
    provider = DeterministicEventParserProvider()

    decision = provider.parse(_build_event(raw_text="\u4eca\u5929\u968f\u4fbf\u8bb0\u4e00\u4e0b\u60f3\u6cd5\u3002"))

    assert decision.status == "fallback"
    assert decision.impact is not None
    assert decision.impact.event_type == "other"
    assert decision.metadata.fallback_reason == "unmatched_text"


def test_deterministic_parser_provider_returns_failed_for_empty_event():
    provider = DeterministicEventParserProvider()

    decision = provider.parse(_build_event(raw_text=None, raw_payload=None))

    assert decision.status == "failed"
    assert decision.impact is None
    assert decision.metadata.fallback_reason == "empty_event"


def test_deterministic_parser_provider_preserves_source_passthrough_fallback():
    provider = DeterministicEventParserProvider()

    decision = provider.parse(_build_event(source="github", raw_text="Repository event synced."))

    assert decision.status == "fallback"
    assert decision.impact is not None
    assert decision.impact.event_type == "github"
    assert decision.metadata.fallback_reason == "source_passthrough"
