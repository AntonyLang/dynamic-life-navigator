"""Brief service implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation
from app.schemas.recommendations import (
    RecommendationBriefItem,
    RecommendationBriefResponse,
    RecommendationBriefSummary,
)

settings = get_settings()


def _active_nodes_query() -> Select[tuple[ActionNode]]:
    """Return the shared query for currently active nodes."""

    return select(ActionNode).where(
        ActionNode.user_id == settings.default_user_id,
        ActionNode.status == "active",
    )


def _node_health(node: ActionNode, latest_expires_at: datetime | None, now: datetime) -> tuple[str, str]:
    """Derive a coarse health label and next hint for brief responses."""

    deadline_soon = node.ddl_timestamp is not None and node.ddl_timestamp <= now + timedelta(days=2)
    annotation_stale = latest_expires_at is None or latest_expires_at <= now

    if deadline_soon or node.dynamic_urgency_score >= 80:
        return "urgent", "Time-sensitive. Consider moving this to the top of your next work block."
    if annotation_stale:
        return "stale", "Context is out of date. Refresh notes or add one concrete next step."
    if node.last_rejected_at is not None and node.last_recommended_at is not None:
        if node.last_rejected_at >= node.last_recommended_at:
            return "cooldown", "Recently rejected. Leave it parked until the context changes."

    return "stable", "This looks healthy. Keep the next step small and specific."


def get_brief(db: Session, request_id: str) -> RecommendationBriefResponse:
    """Return a database-backed brief of the active node set."""

    now = datetime.now(timezone.utc)
    latest_expiry = (
        select(
            NodeAnnotation.node_id,
            func.max(NodeAnnotation.expires_at).label("latest_expires_at"),
        )
        .group_by(NodeAnnotation.node_id)
        .subquery()
    )

    active_projects = db.scalar(
        select(func.count()).select_from(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
            ActionNode.drive_type == "project",
        )
    ) or 0
    active_values = db.scalar(
        select(func.count()).select_from(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
            ActionNode.drive_type == "value",
        )
    ) or 0
    urgent_nodes = db.scalar(
        select(func.count()).select_from(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
            (
                (ActionNode.ddl_timestamp.is_not(None) & (ActionNode.ddl_timestamp <= now + timedelta(days=2)))
                | (ActionNode.dynamic_urgency_score >= 80)
            ),
        )
    ) or 0
    stale_nodes = db.scalar(
        select(func.count()).select_from(ActionNode)
        .outerjoin(latest_expiry, latest_expiry.c.node_id == ActionNode.node_id)
        .where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
            ((latest_expiry.c.latest_expires_at.is_(None)) | (latest_expiry.c.latest_expires_at <= now)),
        )
    ) or 0

    rows = db.execute(
        _active_nodes_query()
        .outerjoin(latest_expiry, latest_expiry.c.node_id == ActionNode.node_id)
        .add_columns(latest_expiry.c.latest_expires_at)
        .order_by(
            case(
                (
                    (ActionNode.ddl_timestamp.is_not(None) & (ActionNode.ddl_timestamp <= now + timedelta(days=2))),
                    0,
                ),
                (ActionNode.dynamic_urgency_score >= 80, 1),
                else_=2,
            ),
            ActionNode.ddl_timestamp.asc().nulls_last(),
            ActionNode.updated_at.desc(),
        )
        .limit(5)
    ).all()

    items = []
    for node, latest_expires_at in rows:
        health, next_hint = _node_health(node, latest_expires_at, now)
        items.append(
            RecommendationBriefItem(
                node_id=str(node.node_id),
                title=node.title,
                status=node.status,
                health=health,
                next_hint=next_hint,
            )
        )

    return RecommendationBriefResponse(
        request_id=request_id,
        summary=RecommendationBriefSummary(
            active_projects=active_projects,
            active_values=active_values,
            urgent_nodes=urgent_nodes,
            stale_nodes=stale_nodes,
        ),
        items=items,
    )
