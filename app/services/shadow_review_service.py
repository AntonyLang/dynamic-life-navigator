"""Operator-facing shadow review summaries for parser and profiling drift."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.models.event_log import EventLog
from app.services.replay_service import CANONICAL_SHADOW_RESULTS

settings = get_settings()


def _empty_summary() -> dict[str, int]:
    return {key: 0 for key in CANONICAL_SHADOW_RESULTS}


def build_parser_shadow_review_report(
    db: Session,
    *,
    user_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Summarize recent parser shadow comparison results for operator review."""

    target_user_id = user_id or settings.default_user_id
    events = db.scalars(
        select(EventLog)
        .where(EventLog.user_id == target_user_id)
        .order_by(EventLog.created_at.desc(), EventLog.event_id.desc())
        .limit(limit)
    ).all()

    comparison_summary = _empty_summary()
    flagged_events: list[dict[str, Any]] = []

    for event in events:
        parse_metadata = dict(event.parse_metadata or {})
        comparison_result = parse_metadata.get("comparison_result")
        if comparison_result not in comparison_summary:
            continue

        comparison_summary[comparison_result] += 1
        if comparison_result not in {"drift", "shadow_failed"}:
            continue

        primary = parse_metadata.get("primary") or {}
        shadow = parse_metadata.get("shadow") or {}
        flagged_events.append(
            {
                "event_id": str(event.event_id),
                "created_at": event.created_at.isoformat(),
                "source": event.source,
                "parse_status": event.parse_status,
                "event_type": (event.parsed_impact or {}).get("event_type"),
                "comparison_result": comparison_result,
                "primary_provider": primary.get("provider"),
                "shadow_provider": shadow.get("shadow_provider"),
                "shadow_status": shadow.get("shadow_status"),
                "shadow_fallback_reason": shadow.get("shadow_fallback_reason"),
            }
        )

    return {
        "user_id": target_user_id,
        "limit": limit,
        "total_events_scanned": len(events),
        "total_compared": sum(comparison_summary.values()),
        "comparison_summary": comparison_summary,
        "flagged_events": flagged_events,
    }


def build_profile_shadow_review_report(
    db: Session,
    *,
    user_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Summarize recent profile shadow comparison results for operator review."""

    target_user_id = user_id or settings.default_user_id
    nodes = db.scalars(
        select(ActionNode)
        .where(ActionNode.user_id == target_user_id)
        .order_by(ActionNode.updated_at.desc(), ActionNode.node_id.desc())
        .limit(limit)
    ).all()

    comparison_summary = _empty_summary()
    flagged_nodes: list[dict[str, Any]] = []

    for node in nodes:
        ai_context = dict(node.ai_context or {})
        comparison_result = ai_context.get("profile_comparison_result")
        if comparison_result not in comparison_summary:
            continue

        comparison_summary[comparison_result] += 1
        if comparison_result not in {"drift", "shadow_failed"}:
            continue

        profile_metadata = ai_context.get("profile_metadata") or {}
        primary = profile_metadata.get("primary") or {}
        shadow = profile_metadata.get("shadow") or {}
        flagged_nodes.append(
            {
                "node_id": str(node.node_id),
                "title": node.title,
                "updated_at": node.updated_at.isoformat(),
                "profiling_status": node.profiling_status,
                "comparison_result": comparison_result,
                "primary_provider": primary.get("provider"),
                "shadow_provider": shadow.get("shadow_provider"),
                "shadow_status": shadow.get("shadow_status"),
                "shadow_fallback_reason": shadow.get("shadow_fallback_reason"),
            }
        )

    return {
        "user_id": target_user_id,
        "limit": limit,
        "total_nodes_scanned": len(nodes),
        "total_compared": sum(comparison_summary.values()),
        "comparison_summary": comparison_summary,
        "flagged_nodes": flagged_nodes,
    }
