"""Background tasks related to action node profiling."""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.node_profile_service import profile_action_node
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.profile_new_node")
def profile_new_node(node_id: str) -> dict[str, str]:
    """Backfill a node profile asynchronously without blocking creation."""

    logger.info("profile_new_node task queued node_id=%s", node_id)
    with SessionLocal() as session:
        return profile_action_node(session, node_id)
