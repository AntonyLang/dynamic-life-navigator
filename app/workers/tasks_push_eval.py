"""Background tasks related to push recommendation evaluation."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.evaluate_push_opportunities")
def evaluate_push_opportunities(trigger_event_id: str | None = None) -> dict[str, str | None]:
    """Placeholder task for push evaluation."""

    logger.info("evaluate_push_opportunities task queued trigger_event_id=%s", trigger_event_id)
    return {"status": "queued", "trigger_event_id": trigger_event_id}
