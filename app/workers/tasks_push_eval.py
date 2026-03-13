"""Background tasks related to push recommendation evaluation."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.push_service import evaluate_push_opportunities as evaluate_push_opportunities_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.evaluate_push_opportunities")
def evaluate_push_opportunities(trigger_event_id: str | None = None) -> dict[str, str | None]:
    """Evaluate whether a weak push recommendation should be generated."""

    log_event(logger, logging.INFO, "push evaluation task started", trigger_event_id=trigger_event_id)
    with SessionLocal() as session:
        result = evaluate_push_opportunities_service(session, trigger_event_id)
    log_event(
        logger,
        logging.INFO,
        "push evaluation task completed",
        trigger_event_id=trigger_event_id,
        status=result.get("status"),
        recommendation_id=result.get("recommendation_id"),
        reason=result.get("reason"),
    )
    return result
