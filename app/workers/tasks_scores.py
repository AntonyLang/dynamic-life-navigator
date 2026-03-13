"""Background tasks related to action node score refresh."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.dynamic_score_service import recalc_dynamic_scores as recalc_dynamic_scores_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.recalc_dynamic_scores")
def recalc_dynamic_scores() -> dict[str, str]:
    """Refresh urgency scores for active nodes."""

    log_event(logger, logging.INFO, "dynamic score task started")
    with SessionLocal() as session:
        result = recalc_dynamic_scores_service(session)
    log_event(
        logger,
        logging.INFO,
        "dynamic score task completed",
        status=result.get("status"),
        updated_count=result.get("updated_count"),
    )
    return {"status": str(result["status"]), "updated_count": str(result["updated_count"])}
