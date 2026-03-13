"""Background tasks related to event parsing."""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.core.logging import log_event
from app.services.event_processing import parse_event_log as parse_event_log_service
from app.workers.tasks_state import apply_state_patch
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.parse_event_log")
def parse_event_log(event_id: str) -> dict[str, str]:
    """Parse an event log and trigger state patching."""

    log_event(logger, logging.INFO, "parse task started", event_id=event_id)
    with SessionLocal() as session:
        impact = parse_event_log_service(session, event_id)

    if getattr(celery_app.conf, "task_always_eager", False):
        apply_state_patch(event_id)
    else:
        apply_state_patch.delay(event_id)

    result = {"status": "parsed", "event_id": event_id, "event_type": str(impact.get("event_type", "other"))}
    log_event(logger, logging.INFO, "parse task completed", event_id=event_id, event_type=result["event_type"])
    return result
