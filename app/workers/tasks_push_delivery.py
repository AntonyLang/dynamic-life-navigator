"""Background tasks related to outbound push delivery."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.push_delivery_service import deliver_push_recommendation as deliver_push_recommendation_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.deliver_push_recommendation")
def deliver_push_recommendation(recommendation_id: str) -> dict[str, str | int | None]:
    """Deliver one generated push recommendation asynchronously."""

    log_event(logger, logging.INFO, "push delivery task started", recommendation_id=recommendation_id)
    with SessionLocal() as session:
        result = deliver_push_recommendation_service(session, recommendation_id)
    log_event(
        logger,
        logging.INFO,
        "push delivery task completed",
        recommendation_id=recommendation_id,
        delivery_status=result.get("status"),
        attempt_count=result.get("attempt_count"),
        reason=result.get("reason"),
    )
    return result
