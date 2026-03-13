"""Asynchronous action-node profiling helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.action_node import ActionNode


@dataclass(frozen=True)
class DerivedNodeProfile:
    mental_energy_required: int
    physical_energy_required: int
    estimated_minutes: int
    recommended_context_tags: list[str]
    confidence_level: str
    ai_context: dict


def derive_node_profile(title: str, tags: list[str], summary: str | None = None) -> DerivedNodeProfile:
    """Derive a conservative-but-useful node profile from stable fields."""

    normalized_title = title.lower()
    normalized_summary = (summary or "").lower()
    normalized_tags = {tag.lower().lstrip("#") for tag in tags}

    mental = 50
    physical = 20
    estimated = 30
    confidence = "low"
    context_tags: set[str] = set()
    profile_signals: list[str] = []

    if normalized_tags.intersection({"exercise", "ride", "run", "workout", "walk"}):
        physical = max(physical, 45)
        estimated = max(estimated, 40)
        confidence = "medium"
        context_tags.add("movement")
        profile_signals.append("movement_tag")

    if normalized_tags.intersection({"study", "coding", "debug", "writing", "research"}):
        mental = max(mental, 70)
        confidence = "medium"
        context_tags.add("deep_focus")
        profile_signals.append("deep_focus_tag")

    if any(token in normalized_title or token in normalized_summary for token in ("organize", "cleanup", "整理", "收拾", "归档")):
        mental = min(mental, 35)
        physical = max(physical, 30)
        estimated = min(max(estimated, 20), 35)
        confidence = "medium"
        context_tags.add("light_admin")
        profile_signals.append("light_admin_hint")

    if any(
        token in normalized_title or token in normalized_summary
        for token in ("review", "report", "debug", "复习", "报告", "调试", "plan", "proposal")
    ):
        mental = max(mental, 72)
        estimated = max(estimated, 45)
        confidence = "medium"
        context_tags.add("deep_focus")
        profile_signals.append("cognitive_work_hint")

    if any(
        token in normalized_title or token in normalized_summary
        for token in ("call", "meeting", "sync", "沟通", "讨论", "会议")
    ):
        mental = max(mental, 55)
        estimated = max(estimated, 25)
        context_tags.add("social")
        profile_signals.append("social_coordination_hint")

    if summary and len(summary) > 120:
        estimated = max(estimated, 45)
        profile_signals.append("long_summary")

    return DerivedNodeProfile(
        mental_energy_required=max(0, min(100, mental)),
        physical_energy_required=max(0, min(100, physical)),
        estimated_minutes=max(10, min(240, estimated)),
        recommended_context_tags=sorted(context_tags),
        confidence_level=confidence,
        ai_context={
            "profile_method": "deterministic_async_v1",
            "profile_signals": profile_signals,
        },
    )


def profile_action_node(db: Session, node_id: str) -> dict[str, str]:
    """Backfill a pending node with a deterministic async profile."""

    node = db.get(ActionNode, node_id)
    if node is None:
        return {"status": "missing", "node_id": node_id}

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

    return {"status": "completed", "node_id": node_id}
