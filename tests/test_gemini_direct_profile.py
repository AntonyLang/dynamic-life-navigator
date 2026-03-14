from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.services.gemini_direct_profile import (
    GEMINI_DIRECT_PROFILE_VERSION,
    GeminiDirectNodeProfileProvider,
)
from app.services.profile_provider import DeterministicNodeProfileProvider
from app.models.action_node import ActionNode

settings = get_settings()


def _build_node(*, title: str, tags: list[str], summary: str | None = None) -> ActionNode:
    return ActionNode(
        node_id=uuid4(),
        user_id=settings.default_user_id,
        drive_type="project",
        status="active",
        title=title,
        summary=summary,
        tags=tags,
        priority_score=50,
        dynamic_urgency_score=0,
        mental_energy_required=50,
        physical_energy_required=20,
        confidence_level="low",
        profiling_status="pending",
        ai_context={},
        metadata_={},
        updated_at=datetime.now(timezone.utc),
    )


def test_gemini_direct_profile_provider_builds_utf8_request_body():
    provider = GeminiDirectNodeProfileProvider(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    node = _build_node(title="整理邮箱归档", tags=["admin"], summary="整理收件箱和归档。")

    request_artifacts = provider.build_request_artifacts(node)
    request_body = provider.build_request_body(provider.build_request_payload(request_artifacts))
    request_text = request_body.decode("utf-8")

    assert "整理邮箱归档" in request_text
    assert "\\u6574\\u7406" not in request_text


def test_gemini_direct_profile_provider_uses_httpx_client_with_trust_env_disabled(monkeypatch):
    provider = GeminiDirectNodeProfileProvider(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    captured: dict[str, object] = {}

    class _DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"candidates": []}

    class _DummyClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self) -> _DummyClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], content: bytes) -> _DummyResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return _DummyResponse()

    monkeypatch.setattr("app.services.gemini_direct_profile.httpx.Client", _DummyClient)

    response = provider._post_generate_content_request(request_body=b"{}")

    assert response == {"candidates": []}
    assert captured["trust_env"] is False
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def test_gemini_direct_profile_provider_returns_validated_success(monkeypatch):
    provider = GeminiDirectNodeProfileProvider(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    node = _build_node(title="整理邮箱归档", tags=["admin"], summary="整理收件箱和归档。")

    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda **_kwargs: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "status": "completed",
                                        "profile": {
                                            "mental_energy_required": 30,
                                            "physical_energy_required": 30,
                                            "estimated_minutes": 25,
                                            "recommended_context_tags": ["light_admin"],
                                            "confidence_level": "medium",
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

    decision = provider.profile(node)

    assert decision.status == "completed"
    assert decision.profile is not None
    assert decision.profile.confidence_level == "medium"
    assert decision.profile.recommended_context_tags == ["light_admin"]
    assert decision.metadata is not None
    assert decision.metadata.provider == "gemini_direct"
    assert decision.metadata.profile_version == GEMINI_DIRECT_PROFILE_VERSION
    assert decision.metadata.fallback_reason is None


def test_gemini_direct_profile_provider_rejects_non_canonical_vocab_and_falls_back(monkeypatch):
    deterministic = DeterministicNodeProfileProvider()
    provider = GeminiDirectNodeProfileProvider(
        deterministic,
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    node = _build_node(title="整理邮箱归档", tags=["admin"], summary="整理收件箱和归档。")
    expected = deterministic.profile(node)

    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda **_kwargs: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "status": "completed",
                                        "profile": {
                                            "mental_energy_required": 30,
                                            "physical_energy_required": 30,
                                            "estimated_minutes": 25,
                                            "recommended_context_tags": ["admin"],
                                            "confidence_level": "uncertain",
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

    decision = provider.profile(node)

    assert decision.status == expected.status
    assert decision.profile is not None
    assert expected.profile is not None
    assert decision.profile.model_dump(mode="json") == expected.profile.model_dump(mode="json")
    assert decision.metadata is not None
    assert decision.metadata.fallback_reason == "validation_error_fallback_after_2_attempts"


def test_gemini_direct_profile_provider_falls_back_after_request_error(monkeypatch):
    deterministic = DeterministicNodeProfileProvider()
    provider = GeminiDirectNodeProfileProvider(
        deterministic,
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemini-2.5-flash",
        timeout_seconds=10,
    )
    node = _build_node(title="Debug the failing parser", tags=["coding", "debug"])
    expected = deterministic.profile(node)
    request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    )

    monkeypatch.setattr(
        provider,
        "_post_generate_content_request",
        lambda **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("boom", request=request)),
    )

    decision = provider.profile(node)

    assert decision.status == expected.status
    assert decision.profile is not None
    assert expected.profile is not None
    assert decision.profile.model_dump(mode="json") == expected.profile.model_dump(mode="json")
    assert decision.metadata is not None
    assert decision.metadata.fallback_reason == "request_error_fallback_after_2_attempts"
    assert decision.metadata.error_detail == "ConnectError"
