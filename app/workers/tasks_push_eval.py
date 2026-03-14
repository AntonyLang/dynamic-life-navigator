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

    if result.get("status") == "generated" and result.get("recommendation_id") is not None:
        from app.workers.tasks_push_delivery import deliver_push_recommendation

        recommendation_id = str(result["recommendation_id"])
        if getattr(celery_app.conf, "task_always_eager", False):
            delivery_result = deliver_push_recommendation(recommendation_id)
            result["delivery_status"] = str(delivery_result.get("status"))
        else:
            deliver_push_recommendation.delay(recommendation_id)
            result["delivery_status"] = "queued"

    log_event(
        logger,
        logging.INFO,
        "push evaluation task completed",
        trigger_event_id=trigger_event_id,
        status=result.get("status"),
        recommendation_id=result.get("recommendation_id"),
        reason=result.get("reason"),
        delivery_status=result.get("delivery_status"),
    )
    return result
