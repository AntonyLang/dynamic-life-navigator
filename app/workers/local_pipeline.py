"""Local background pipeline fallback for development without Celery workers."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.event_processing import apply_state_patch_from_event, parse_event_log
from app.services.push_service import evaluate_push_opportunities

logger = logging.getLogger(__name__)


def run_local_event_pipeline(event_id: str) -> None:
    """Process an ingested event without Redis/Celery, using FastAPI background tasks."""

    log_event(logger, logging.INFO, "local event pipeline started", event_id=event_id)

    try:
        with SessionLocal() as session:
            impact = parse_event_log(session, event_id)

        with SessionLocal() as session:
            snapshot = apply_state_patch_from_event(session, event_id)

        with SessionLocal() as session:
            push_result = evaluate_push_opportunities(session, event_id)

        log_event(
            logger,
            logging.INFO,
            "local event pipeline completed",
            event_id=event_id,
            event_type=str(impact.get("event_type", "other")),
            focus_mode=snapshot.focus_mode,
            mental_energy=snapshot.mental_energy,
            physical_energy=snapshot.physical_energy,
            push_status=push_result.get("status"),
        )
    except Exception:
        logger.exception("local event pipeline failed event_id=%s", event_id)
