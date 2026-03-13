"""Dynamic score recalculation helpers for action nodes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.action_node import ActionNode

logger = logging.getLogger(__name__)
settings = get_settings()


def _deadline_urgency(node: ActionNode, now: datetime) -> int:
    """Compute urgency contribution from deadline distance."""

    if node.ddl_timestamp is None:
        return 0
    if node.ddl_timestamp <= now:
        return 100

    remaining = node.ddl_timestamp - now
    if remaining <= timedelta(hours=12):
        return 90
    if remaining <= timedelta(days=1):
        return 75
    if remaining <= timedelta(days=3):
        return 55
    if remaining <= timedelta(days=7):
        return 30
    return 10


def _staleness_bonus(node: ActionNode, now: datetime) -> int:
    """Compute a small boost for nodes that have not been surfaced recently."""

    if node.last_recommended_at is None:
        return 20

    silence = now - node.last_recommended_at
    if silence >= timedelta(days=14):
        return 25
    if silence >= timedelta(days=7):
        return 15
    if silence >= timedelta(days=3):
        return 8
    return 0


def recalc_dynamic_scores(db: Session) -> dict[str, int | str]:
    """Refresh dynamic urgency scores for the current active node set."""

    now = datetime.now(timezone.utc)
    active_nodes = db.scalars(
        select(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
        )
    ).all()

    updated_count = 0
    for node in active_nodes:
        deadline_component = _deadline_urgency(node, now)
        stale_component = _staleness_bonus(node, now)
        recalculated = min(100, max(deadline_component, stale_component))

        if node.dynamic_urgency_score != recalculated:
            node.dynamic_urgency_score = recalculated
            node.updated_at = now
            db.add(node)
            updated_count += 1

    db.commit()
    log_event(
        logger,
        logging.INFO,
        "dynamic scores recalculated",
        user_id=settings.default_user_id,
        active_count=len(active_nodes),
        updated_count=updated_count,
    )
    return {"status": "completed", "updated_count": updated_count}
