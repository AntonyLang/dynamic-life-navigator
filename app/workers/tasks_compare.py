"""Background tasks related to non-authoritative parser comparison."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.event_processing import compare_shadow_parser_decision
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.compare_parser_decision")
def compare_parser_decision(event_id: str) -> dict[str, str]:
    """Run the configured shadow parser and record comparison metadata."""

    log_event(logger, logging.INFO, "shadow compare task started", event_id=event_id)
    with SessionLocal() as session:
        result = compare_shadow_parser_decision(session, event_id)

    log_event(
        logger,
        logging.INFO,
        "shadow compare task completed",
        event_id=event_id,
        compare_status=result.get("status"),
        comparison_result=result.get("comparison_result"),
        reason=result.get("reason"),
    )
    return {key: str(value) for key, value in result.items()}
