"""Asynchronous action-node profiling helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.action_node import ActionNode
from app.schemas.parsing import NodeProfileDecisionDTO, NodeProfileOutputDTO
from app.services.profile_provider import (
    derive_deterministic_node_profile,
    get_node_profile_provider,
    get_shadow_node_profile_provider,
)


def derive_node_profile(title: str, tags: list[str], summary: str | None = None) -> NodeProfileOutputDTO:
    """Derive the conservative deterministic node profile used for safe prefills."""

    return derive_deterministic_node_profile(title, tags, summary)


def _profile_metadata_dict(decision: NodeProfileDecisionDTO) -> dict[str, Any]:
    if decision.metadata is None:
        return {}
    return decision.metadata.model_dump(mode="json")


def _get_profile_metadata(ai_context: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(ai_context or {})
    metadata = context.get("profile_metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _set_primary_profile_metadata(ai_context: dict[str, Any] | None, decision: NodeProfileDecisionDTO) -> dict[str, Any]:
    context = dict(ai_context or {})
    metadata = _get_profile_metadata(context)
    metadata["primary"] = _profile_metadata_dict(decision)
    context["profile_metadata"] = metadata
    return context


def _normalize_context_tags(profile: NodeProfileOutputDTO) -> tuple[str, ...]:
    return tuple(sorted(profile.recommended_context_tags))


def _is_exact_profile_match(primary: NodeProfileOutputDTO, shadow: NodeProfileOutputDTO) -> bool:
    return (
        primary.mental_energy_required == shadow.mental_energy_required
        and primary.physical_energy_required == shadow.physical_energy_required
        and primary.estimated_minutes == shadow.estimated_minutes
        and primary.confidence_level == shadow.confidence_level
        and _normalize_context_tags(primary) == _normalize_context_tags(shadow)
    )


def _is_compatible_profile_match(primary: NodeProfileOutputDTO, shadow: NodeProfileOutputDTO) -> bool:
    return (
        abs(primary.mental_energy_required - shadow.mental_energy_required) <= 5
        and abs(primary.physical_energy_required - shadow.physical_energy_required) <= 5
        and abs(primary.estimated_minutes - shadow.estimated_minutes) <= 10
        and primary.confidence_level == shadow.confidence_level
        and _normalize_context_tags(primary) == _normalize_context_tags(shadow)
    )


def _classify_shadow_profile_comparison(
    primary: NodeProfileDecisionDTO,
    shadow: NodeProfileDecisionDTO,
) -> str:
    if (
        shadow.metadata is None
        or shadow.metadata.fallback_reason is not None
        or shadow.status != "completed"
        or shadow.profile is None
        or primary.profile is None
    ):
        return "shadow_failed"
    if _is_exact_profile_match(primary.profile, shadow.profile):
        return "exact_match"
    if _is_compatible_profile_match(primary.profile, shadow.profile):
        return "compatible_match"
    return "drift"


def compare_shadow_profile_decision(db: Session, node_id: str) -> dict[str, Any]:
    """Compare the configured shadow node profiler against the authoritative profile."""

    node = db.get(ActionNode, node_id)
    if node is None:
        return {"status": "missing", "node_id": node_id}

    shadow_provider = get_shadow_node_profile_provider()
    if shadow_provider is None:
        return {"status": "skipped", "node_id": node_id, "comparison_result": None}

    primary_metadata = _get_profile_metadata(node.ai_context).get("primary")
    if not isinstance(primary_metadata, dict):
        return {"status": "skipped", "node_id": node_id, "comparison_result": None}

    primary = NodeProfileDecisionDTO(
        status="completed",
        node_id=str(node.node_id),
        profile=NodeProfileOutputDTO(
            mental_energy_required=node.mental_energy_required,
            physical_energy_required=node.physical_energy_required,
            estimated_minutes=node.estimated_minutes or 30,
            recommended_context_tags=node.recommended_context_tags or [],
            confidence_level=node.confidence_level,
            ai_context=dict(node.ai_context or {}),
        ),
        metadata=primary_metadata,
    )

    shadow = shadow_provider.profile(node)
    comparison_result = _classify_shadow_profile_comparison(primary, shadow)

    ai_context = dict(node.ai_context or {})
    metadata = _get_profile_metadata(ai_context)
    metadata["shadow"] = {
        "shadow_provider": shadow.metadata.provider if shadow.metadata is not None else shadow_provider.name,
        "shadow_profile_version": shadow.metadata.profile_version if shadow.metadata is not None else None,
        "shadow_prompt_version": shadow.metadata.prompt_version if shadow.metadata is not None else None,
        "shadow_model_name": shadow.metadata.model_name if shadow.metadata is not None else None,
        "shadow_status": shadow.status,
        "shadow_fallback_reason": shadow.metadata.fallback_reason if shadow.metadata is not None else None,
        "shadow_error_detail": shadow.metadata.error_detail if shadow.metadata is not None else None,
    }
    ai_context["profile_metadata"] = metadata
    ai_context["profile_comparison_result"] = comparison_result
    node.ai_context = ai_context
    node.updated_at = datetime.now(timezone.utc)
    db.add(node)
    db.commit()

    return {
        "status": "completed",
        "node_id": node_id,
        "comparison_result": comparison_result,
        "shadow_provider": shadow_provider.name,
    }


def profile_action_node(db: Session, node_id: str) -> dict[str, Any]:
    """Backfill a pending node with an authoritative profile and optional shadow compare."""

    node = db.get(ActionNode, node_id)
    if node is None:
        return NodeProfileDecisionDTO(status="missing", node_id=node_id, profile=None, metadata=None).model_dump(mode="json")

    decision = get_node_profile_provider().profile(node)
    if decision.profile is None:
        return decision.model_dump(mode="json")

    profile = decision.profile
    now = datetime.now(timezone.utc)
    node.mental_energy_required = profile.mental_energy_required
    node.physical_energy_required = profile.physical_energy_required
    node.estimated_minutes = profile.estimated_minutes
    node.recommended_context_tags = profile.recommended_context_tags
    node.confidence_level = profile.confidence_level
    node.profiling_status = "completed"
    node.profiled_at = now
    node.ai_context = _set_primary_profile_metadata(
        {**(node.ai_context or {}), **profile.ai_context},
        decision,
    )
    node.updated_at = now
    db.add(node)
    db.commit()

    compare_shadow_profile_decision(db, node_id)
    db.refresh(node)

    return NodeProfileDecisionDTO(
        status="completed",
        node_id=node_id,
        profile=profile,
        metadata=decision.metadata,
    ).model_dump(mode="json")
