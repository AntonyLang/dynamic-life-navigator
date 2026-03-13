"""Asynchronous action-node profiling helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.action_node import ActionNode
from app.schemas.parsing import NodeProfileDecisionDTO, NodeProfileOutputDTO
from app.services.signal_catalog import collect_signal_names


def derive_node_profile(title: str, tags: list[str], summary: str | None = None) -> NodeProfileOutputDTO:
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
            "profile_method": "deterministic_async_v2",
            "profile_signals": profile_signals,
        },
    )


def profile_action_node(db: Session, node_id: str) -> dict[str, str]:
    """Backfill a pending node with a deterministic async profile."""

    node = db.get(ActionNode, node_id)
    if node is None:
        return NodeProfileDecisionDTO(status="missing", node_id=node_id, profile=None).model_dump(mode="json")

    profile = derive_node_profile(node.title, node.tags or [], node.summary)
    now = datetime.now(timezone.utc)
    node.mental_energy_required = profile.mental_energy_required
    node.physical_energy_required = profile.physical_energy_required
    node.estimated_minutes = profile.estimated_minutes
    node.recommended_context_tags = profile.recommended_context_tags
    node.confidence_level = profile.confidence_level
    node.profiling_status = "completed"
    node.profiled_at = now
    node.ai_context = {**(node.ai_context or {}), **profile.ai_context}
    node.updated_at = now
    db.add(node)
    db.commit()

    return NodeProfileDecisionDTO(status="completed", node_id=node_id, profile=profile).model_dump(mode="json")
