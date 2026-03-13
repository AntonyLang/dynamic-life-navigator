from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.prompts.structured_event_parser_assets import (
    build_structured_event_parser_model_response_schema,
)
from app.services.gemini_direct_parser import (
    GEMINI_DIRECT_PARSER_VERSION,
    GeminiDirectEventParserProvider,
)
from app.services.parser_provider import (
    DeterministicEventParserProvider,
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


def test_gemini_direct_provider_builds_generate_content_payload():
    provider = GeminiDirectEventParserProvider(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    event = _build_event(raw_text="I just finished a heavy debugging session and feel tired.")

    request_artifacts = provider.build_request_artifacts(event)
    request_payload = provider.build_request_payload(request_artifacts)

    assert request_payload["systemInstruction"]["parts"][0]["text"] == request_artifacts["system_prompt"]
    assert request_payload["contents"][0]["parts"][0]["text"] == request_artifacts["user_prompt"]
    assert request_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert request_payload["generationConfig"]["responseJsonSchema"] == build_structured_event_parser_model_response_schema()
    assert "$defs" not in request_payload["generationConfig"]["responseJsonSchema"]
    assert "metadata" not in request_payload["generationConfig"]["responseJsonSchema"]["properties"]


def test_gemini_direct_provider_falls_back_without_api_key():
    deterministic = DeterministicEventParserProvider()
    provider = GeminiDirectEventParserProvider(
        deterministic,
        api_key=None,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")
    expected = deterministic.parse(event)

    decision = provider.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.provider == "gemini_direct"
    assert decision.metadata.parser_version == GEMINI_DIRECT_PARSER_VERSION
    assert decision.metadata.fallback_reason == "missing_gemini_api_key"


def test_gemini_direct_provider_returns_validated_success(monkeypatch):
    provider = GeminiDirectEventParserProvider(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")

    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda _payload: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "status": "success",
                                        "impact": {
                                            "event_summary": "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002",
                                            "event_type": "chat_update",
                                            "mental_delta": -20,
                                            "physical_delta": 0,
                                            "focus_mode": "tired",
                                            "tags": ["mental_load"],
                                            "should_offer_pull_hint": True,
                                            "confidence": 0.7,
                                        },
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    decision = provider.parse(event)

    assert decision.status == "success"
    assert decision.impact is not None
    assert decision.impact.focus_mode == "tired"
    assert decision.metadata.provider == "gemini_direct"
    assert decision.metadata.parser_version == GEMINI_DIRECT_PARSER_VERSION
    assert decision.metadata.model_name == "gemini-2.5-flash"
    assert decision.metadata.fallback_reason is None


def test_gemini_direct_provider_falls_back_after_invalid_json(monkeypatch):
    deterministic = DeterministicEventParserProvider()
    provider = GeminiDirectEventParserProvider(
        deterministic,
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    event = _build_event(raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002")
    expected = deterministic.parse(event)

    monkeypatch.setenv("STRUCTURED_PARSER_VALIDATION_RETRIES", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda _payload: {"candidates": [{"content": {"parts": [{"text": "{not-json"}]}}]},
    )

    decision = provider.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.fallback_reason == "invalid_json_response_fallback_after_2_attempts"
    get_settings.cache_clear()


def test_gemini_direct_provider_falls_back_after_request_error(monkeypatch):
    deterministic = DeterministicEventParserProvider()
    provider = GeminiDirectEventParserProvider(
        deterministic,
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    event = _build_event(raw_text="I just finished a heavy debugging session and feel tired.")
    expected = deterministic.parse(event)
    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    )

    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda _payload: (_ for _ in ()).throw(httpx.ConnectError("boom", request=request)),
    )

    decision = provider.parse(event)

    assert decision.status == expected.status
    assert decision.impact is not None
    assert expected.impact is not None
    assert decision.impact.model_dump(mode="json") == expected.impact.model_dump(mode="json")
    assert decision.metadata.fallback_reason == "request_error_fallback_after_2_attempts"
    assert decision.metadata.error_detail == "ConnectError"


def test_get_event_parser_provider_supports_gemini_direct(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "gemini_direct")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("STRUCTURED_PARSER_TIMEOUT_SECONDS", "9")
    get_settings.cache_clear()

    provider = get_event_parser_provider()

    assert provider.name == "gemini_direct"
    assert isinstance(provider, GeminiDirectEventParserProvider)
    assert provider.parser_version == GEMINI_DIRECT_PARSER_VERSION
    get_settings.cache_clear()
