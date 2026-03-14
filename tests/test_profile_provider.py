from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.prompts.structured_node_profile_assets import (
    STRUCTURED_NODE_PROFILE_PROMPT_VERSION,
    build_structured_node_profile_model_response_schema,
    build_structured_node_profile_request,
    load_structured_node_profile_system_prompt,
)
from app.services.gemini_direct_profile import GeminiDirectNodeProfileProvider
from app.services.profile_provider import (
    DETERMINISTIC_PROFILE_VERSION,
    DeterministicNodeProfileProvider,
    derive_deterministic_node_profile,
    get_node_profile_provider,
    get_shadow_node_profile_provider,
)

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


def test_derive_deterministic_node_profile_supports_chinese_light_admin():
    profile = derive_deterministic_node_profile("整理邮箱归档", [], None)

    assert profile.mental_energy_required <= 35
    assert profile.physical_energy_required >= 30
    assert "light_admin" in profile.recommended_context_tags
    assert profile.confidence_level == "medium"


def test_deterministic_node_profile_provider_returns_completed_decision():
    provider = DeterministicNodeProfileProvider()
    node = _build_node(title="Debug the failing parser", tags=["coding", "debug"])

    decision = provider.profile(node)

    assert decision.status == "completed"
    assert decision.profile is not None
    assert decision.profile.mental_energy_required >= 70
    assert "deep_focus" in decision.profile.recommended_context_tags
    assert decision.metadata is not None
    assert decision.metadata.provider == "deterministic"
    assert decision.metadata.profile_version == DETERMINISTIC_PROFILE_VERSION


def test_structured_node_profile_assets_expose_prompt_and_schema():
    node = _build_node(
        title="Prepare review report for parser regression",
        tags=["coding"],
        summary="Review the failure modes and propose the next patch plan.",
    )

    system_prompt = load_structured_node_profile_system_prompt()
    request_artifacts = build_structured_node_profile_request(node, "demo-model")
    response_schema = build_structured_node_profile_model_response_schema()

    assert "structured async node profiler" in system_prompt.lower()
    assert request_artifacts["metadata"]["prompt_version"] == STRUCTURED_NODE_PROFILE_PROMPT_VERSION
    assert request_artifacts["metadata"]["model_name"] == "demo-model"
    assert "allowed_context_tags: movement, deep_focus, light_admin, social" in request_artifacts["user_prompt"]
    assert "Canonical examples:" in request_artifacts["user_prompt"]
    assert "recommended_context_tags=[light_admin]" in request_artifacts["user_prompt"]
    assert "recommended_context_tags=[deep_focus]" in request_artifacts["user_prompt"]
    schema_json = json.dumps(response_schema, ensure_ascii=False)
    assert '"light_admin"' in schema_json
    assert '"medium"' in schema_json


def test_get_node_profile_provider_defaults_to_deterministic(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    get_settings.cache_clear()

    provider = get_node_profile_provider()

    assert provider.name == "deterministic"
    get_settings.cache_clear()


def test_get_shadow_node_profile_provider_uses_configured_provider(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("STRUCTURED_PROFILE_MODEL_NAME", "gemini-2.5-flash")
    get_settings.cache_clear()

    provider = get_shadow_node_profile_provider()

    assert provider is not None
    assert provider.name == "gemini_direct"
    assert isinstance(provider, GeminiDirectNodeProfileProvider)
    get_settings.cache_clear()


def test_get_shadow_node_profile_provider_skips_when_same_as_primary(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "gemini_direct")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")
    get_settings.cache_clear()

    provider = get_shadow_node_profile_provider()

    assert provider is None
    get_settings.cache_clear()
