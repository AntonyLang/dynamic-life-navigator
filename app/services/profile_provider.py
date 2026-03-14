"""Profile-provider boundary for deterministic and model-backed node profiling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.core.config import get_settings
from app.schemas.parsing import NodeProfileDecisionDTO, NodeProfileOutputDTO
from app.services.signal_catalog import collect_signal_names

if TYPE_CHECKING:
    from app.models.action_node import ActionNode


DETERMINISTIC_PROFILE_VERSION = "deterministic_async_v2"


class NodeProfileProvider(Protocol):
    """Small provider boundary so structured profiling can slot in safely."""

    name: str
    profile_version: str

    def profile(self, node: ActionNode) -> NodeProfileDecisionDTO:
        """Produce a validated profile decision for a stored action node."""


def derive_deterministic_node_profile(title: str, tags: list[str], summary: str | None = None) -> NodeProfileOutputDTO:
    """Derive a conservative-but-useful node profile from stable fields."""

    normalized_title = title.lower()
    normalized_summary = (summary or "").lower()
    normalized_tags = [tag.lower().lstrip("#") for tag in tags]
    matched_signals = collect_signal_names(normalized_title, normalized_summary, " ".join(normalized_tags))

    mental = 50
    physical = 20
    estimated = 30
    confidence = "low"
    context_tags: set[str] = set()
    profile_signals: list[str] = []

    if "movement" in matched_signals:
        physical = max(physical, 45)
        estimated = max(estimated, 40)
        confidence = "medium"
        context_tags.add("movement")
        profile_signals.append("movement_signal")

    if "mental_load" in matched_signals or "deep_focus" in matched_signals:
        mental = max(mental, 70)
        confidence = "medium"
        context_tags.add("deep_focus")
        profile_signals.append("deep_focus_signal")

    if "light_admin" in matched_signals:
        mental = min(mental, 35)
        physical = max(physical, 30)
        estimated = min(max(estimated, 20), 35)
        confidence = "medium"
        context_tags.add("light_admin")
        profile_signals.append("light_admin_signal")

    if "deep_focus" in matched_signals:
        mental = max(mental, 72)
        estimated = max(estimated, 45)
        confidence = "medium"
        context_tags.add("deep_focus")
        profile_signals.append("cognitive_work_signal")

    if "coordination" in matched_signals:
        mental = max(mental, 55)
        estimated = max(estimated, 25)
        context_tags.add("social")
        profile_signals.append("social_coordination_signal")

    if summary and len(summary) > 120:
        estimated = max(estimated, 45)
        profile_signals.append("long_summary")

    return NodeProfileOutputDTO(
        mental_energy_required=max(0, min(100, mental)),
        physical_energy_required=max(0, min(100, physical)),
        estimated_minutes=max(10, min(240, estimated)),
        recommended_context_tags=sorted(context_tags),
        confidence_level=confidence,
        ai_context={
            "profile_method": DETERMINISTIC_PROFILE_VERSION,
            "profile_signals": profile_signals,
        },
    )


class DeterministicNodeProfileProvider:
    """Rule-driven async node profile provider used by default."""

    name = "deterministic"
    profile_version = DETERMINISTIC_PROFILE_VERSION

    def profile(self, node: ActionNode) -> NodeProfileDecisionDTO:
        profile = derive_deterministic_node_profile(node.title, node.tags or [], node.summary)
        return NodeProfileDecisionDTO(
            status="completed",
            node_id=str(node.node_id),
            profile=profile,
            metadata={
                "provider": self.name,
                "profile_version": self.profile_version,
            },
        )


_DETERMINISTIC_PROFILE_PROVIDER = DeterministicNodeProfileProvider()


def build_node_profile_provider(provider_name: str) -> NodeProfileProvider:
    """Build a named node profile provider using the current settings snapshot."""

    settings = get_settings()
    if provider_name == "gemini_direct":
        from app.services.gemini_direct_profile import GeminiDirectNodeProfileProvider

        return GeminiDirectNodeProfileProvider(
            _DETERMINISTIC_PROFILE_PROVIDER,
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model_name=settings.structured_profile_model_name,
            timeout_seconds=settings.structured_profile_timeout_seconds,
        )
    return _DETERMINISTIC_PROFILE_PROVIDER


def get_node_profile_provider() -> NodeProfileProvider:
    """Return the configured authoritative profile provider."""

    return build_node_profile_provider(get_settings().profile_provider)


def get_shadow_node_profile_provider() -> NodeProfileProvider | None:
    """Return the configured shadow profile provider if enabled."""

    settings = get_settings()
    if not settings.profile_shadow_enabled:
        return None
    if settings.profile_shadow_provider == settings.profile_provider:
        return None
    return build_node_profile_provider(settings.profile_shadow_provider)
