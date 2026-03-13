from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.prompts.structured_event_parser_assets import (
    STRUCTURED_EVENT_PARSER_PROMPT_VERSION,
    build_structured_event_parser_request,
    build_structured_event_parser_response_schema,
    load_structured_event_parser_system_prompt,
)
from app.services.parser_provider import (
    DETERMINISTIC_PARSER_VERSION,
    DeterministicEventParserProvider,
    STRUCTURED_MODEL_SHELL_PARSER_VERSION,
    STRUCTURED_STUB_PARSER_VERSION,
    STRUCTURED_STUB_PROMPT_VERSION,
    StructuredModelShellEventParserProvider,
    StructuredStubEventParserProvider,
    get_event_parser_provider,
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


def test_structured_stub_provider_delegates_without_changing_impact():
    deterministic = DeterministicEventParserProvider()
    stub = StructuredStubEventParserProvider(deterministic)
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")

    expected = deterministic.parse(event)
    decision = stub.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.provider == "structured_stub"
    assert decision.metadata.parser_version == STRUCTURED_STUB_PARSER_VERSION
    assert decision.metadata.prompt_version == STRUCTURED_STUB_PROMPT_VERSION
    assert decision.metadata.model_name == "stub"


def test_structured_stub_provider_retries_then_accepts_valid_candidate(monkeypatch):
    deterministic = DeterministicEventParserProvider()
    stub = StructuredStubEventParserProvider(deterministic)
    event = _build_event(raw_text="I just finished a heavy debugging session and feel tired.")
    call_count = {"count": 0}

    def fake_candidate_payload(_event, attempt):
        call_count["count"] += 1
        if attempt == 1:
            return {
                "status": "success",
                "impact": {
                    "event_summary": 123,
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                "metadata": {
                    "provider": "structured_stub",
                    "parser_version": STRUCTURED_STUB_PARSER_VERSION,
                    "prompt_version": STRUCTURED_STUB_PROMPT_VERSION,
                    "model_name": "stub",
                },
            }
        return {
            "status": "success",
            "impact": {
                "event_summary": "I just finished a heavy debugging session and feel tired.",
                "event_type": "chat_update",
                "mental_delta": -20,
                "physical_delta": 0,
                "focus_mode": "tired",
                "tags": ["mental_load"],
                "should_offer_pull_hint": True,
                "confidence": 0.7,
            },
            "metadata": {
                "provider": "structured_stub",
                "parser_version": STRUCTURED_STUB_PARSER_VERSION,
                "prompt_version": STRUCTURED_STUB_PROMPT_VERSION,
                "model_name": "stub",
            },
        }

    monkeypatch.setattr(stub, "_build_candidate_payload", fake_candidate_payload)
    monkeypatch.setenv("STRUCTURED_PARSER_VALIDATION_RETRIES", "1")
    get_settings.cache_clear()

    decision = stub.parse(event)

    assert call_count["count"] == 2
    assert decision.status == "success"
    assert decision.impact is not None
    assert decision.impact.event_type == "chat_update"
    get_settings.cache_clear()


def test_structured_stub_provider_falls_back_after_validation_failures(monkeypatch):
    deterministic = DeterministicEventParserProvider()
    stub = StructuredStubEventParserProvider(deterministic)
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")
    expected = deterministic.parse(event)

    monkeypatch.setattr(
        stub,
        "_build_candidate_payload",
        lambda _event, attempt: {
            "status": "success",
            "impact": {
                "event_summary": [],
                "event_type": "chat_update",
                "mental_delta": -20,
                "physical_delta": 0,
                "focus_mode": "tired",
                "tags": ["mental_load"],
                "should_offer_pull_hint": True,
                "confidence": 0.7,
            },
            "metadata": {
                "provider": "structured_stub",
                "parser_version": STRUCTURED_STUB_PARSER_VERSION,
                "prompt_version": STRUCTURED_STUB_PROMPT_VERSION,
                "model_name": "stub",
            },
        },
    )
    monkeypatch.setenv("STRUCTURED_PARSER_VALIDATION_RETRIES", "1")
    get_settings.cache_clear()

    decision = stub.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.provider == "structured_stub"
    assert decision.metadata.fallback_reason == "validation_error_fallback_after_2_attempts"
    get_settings.cache_clear()


def test_structured_event_parser_assets_expose_prompt_and_schema():
    event = _build_event(raw_text="I just finished a heavy debugging session and feel tired.")

    system_prompt = load_structured_event_parser_system_prompt()
    request_artifacts = build_structured_event_parser_request(event, "demo-model")
    response_schema = build_structured_event_parser_response_schema()

    assert "structured event parser" in system_prompt.lower()
    assert request_artifacts["metadata"]["prompt_version"] == STRUCTURED_EVENT_PARSER_PROMPT_VERSION
    assert request_artifacts["metadata"]["model_name"] == "demo-model"
    assert "raw_text: I just finished a heavy debugging session and feel tired." in request_artifacts["user_prompt"]
    assert response_schema["title"] == "ParserDecisionDTO"
    assert "status" in response_schema["properties"]
    assert "metadata" in response_schema["properties"]


def test_structured_model_shell_provider_builds_request_artifacts():
    provider = StructuredModelShellEventParserProvider(model_name="demo-model")
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")

    request_artifacts = provider.build_request_artifacts(event)

    assert request_artifacts["metadata"]["prompt_version"] == STRUCTURED_EVENT_PARSER_PROMPT_VERSION
    assert request_artifacts["metadata"]["model_name"] == "demo-model"
    assert "response_schema" in request_artifacts
    assert "system_prompt" in request_artifacts


def test_structured_model_shell_provider_falls_back_without_model_call(monkeypatch):
    deterministic = DeterministicEventParserProvider()
    provider = StructuredModelShellEventParserProvider(deterministic, model_name="demo-model")
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")
    expected = deterministic.parse(event)

    decision = provider.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.provider == "structured_model_shell"
    assert decision.metadata.parser_version == STRUCTURED_MODEL_SHELL_PARSER_VERSION
    assert decision.metadata.prompt_version == STRUCTURED_EVENT_PARSER_PROMPT_VERSION
    assert decision.metadata.model_name == "demo-model"
    assert decision.metadata.fallback_reason == "model_call_not_implemented"


def test_get_event_parser_provider_defaults_to_deterministic(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "deterministic")
    get_settings.cache_clear()

    provider = get_event_parser_provider()

    assert provider.name == "deterministic"
    get_settings.cache_clear()


def test_get_event_parser_provider_supports_structured_stub(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "structured_stub")
    get_settings.cache_clear()

    provider = get_event_parser_provider()

    assert provider.name == "structured_stub"
    get_settings.cache_clear()


def test_get_event_parser_provider_supports_structured_model_shell(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "structured_model_shell")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "demo-model")
    get_settings.cache_clear()

    provider = get_event_parser_provider()

    assert provider.name == "structured_model_shell"
    assert isinstance(provider, StructuredModelShellEventParserProvider)
    get_settings.cache_clear()
