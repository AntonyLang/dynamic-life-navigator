"""Node annotation enrichment helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation

logger = logging.getLogger(__name__)
settings = get_settings()
SYSTEM_ANNOTATION_SOURCE = "system_enricher"
SYSTEM_ANNOTATION_TYPE = "node_summary"


def _annotation_hint(node: ActionNode) -> str:
    """Generate a lightweight next-step hint without external enrichment."""

    if node.ddl_timestamp is not None:
        return "Deadline-aware node. Keep the next step concrete and time-bounded."
    if "deep_focus" in node.recommended_context_tags:
        return "Best used in a focused session with minimal interruptions."
    if "movement" in node.recommended_context_tags:
        return "Works best when you want physical movement instead of more screen time."
    return "Keep the next action small enough to start immediately."


def _freshness_score(node: ActionNode, now: datetime) -> int:
    """Approximate freshness based on urgency and recent updates."""

    score = 60
    if node.ddl_timestamp is not None and node.ddl_timestamp <= now + timedelta(days=2):
        score += 20
    if node.last_recommended_at is not None and node.last_recommended_at >= now - timedelta(days=1):
        score += 10
    return min(score, 100)


def _expires_at(node: ActionNode, now: datetime) -> datetime:
    """Choose a short expiry for urgent nodes and a longer one otherwise."""

    if node.ddl_timestamp is not None and node.ddl_timestamp <= now + timedelta(days=2):
        return now + timedelta(hours=6)
    return now + timedelta(days=2)


def enrich_active_nodes(db: Session) -> dict[str, int]:
    """Refresh lightweight system annotations for the active node set."""

    now = datetime.now(timezone.utc)
    active_nodes = db.scalars(
        select(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
        )
    ).all()

    if not active_nodes:
        log_event(logger, logging.INFO, "node enrichment completed", user_id=settings.default_user_id, enriched_count=0)
        return {"status": "completed", "enriched_count": 0}

    active_node_ids = [node.node_id for node in active_nodes]
    db.execute(
        delete(NodeAnnotation).where(
            NodeAnnotation.node_id.in_(active_node_ids),
            NodeAnnotation.source == SYSTEM_ANNOTATION_SOURCE,
            NodeAnnotation.annotation_type == SYSTEM_ANNOTATION_TYPE,
        )
    )

    for node in active_nodes:
        current_node = db.get(ActionNode, node.node_id)
        if current_node is None or current_node.status != "active":
            continue
        db.add(
            NodeAnnotation(
                node_id=current_node.node_id,
                annotation_type=SYSTEM_ANNOTATION_TYPE,
                source=SYSTEM_ANNOTATION_SOURCE,
                content={
                    "title": current_node.title,
                    "summary": current_node.summary,
                    "drive_type": current_node.drive_type,
                    "recommended_context_tags": current_node.recommended_context_tags,
                    "hint": _annotation_hint(current_node),
                },
                freshness_score=_freshness_score(current_node, now),
                fetched_at=now,
                expires_at=_expires_at(current_node, now),
                fetch_status="success",
            )
        )

    db.commit()
    log_event(
        logger,
        logging.INFO,
        "node enrichment completed",
        user_id=settings.default_user_id,
        enriched_count=len(active_nodes),
    )
    return {"status": "completed", "enriched_count": len(active_nodes)}
