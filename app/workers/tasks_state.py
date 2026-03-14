"""Background tasks related to state updates."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.event_processing import apply_state_patch_from_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.apply_state_patch")
def apply_state_patch(event_id: str) -> dict[str, str]:
    """Apply a parsed event impact onto the current state snapshot."""

    log_event(logger, logging.INFO, "state patch task started", event_id=event_id)
    with SessionLocal() as session:
        snapshot = apply_state_patch_from_event(session, event_id)

    from app.workers.tasks_compare import compare_parser_decision
    from app.workers.tasks_push_eval import evaluate_push_opportunities
    from app.core.config import get_settings

    settings = get_settings()

    if getattr(celery_app.conf, "task_always_eager", False):
        evaluate_push_opportunities(event_id)
        if settings.parser_shadow_enabled:
            compare_parser_decision(event_id)
    else:
        evaluate_push_opportunities.delay(event_id)
        if settings.parser_shadow_enabled:
            compare_parser_decision.delay(event_id)

    result = {
        "status": "applied",
        "event_id": event_id,
        "focus_mode": snapshot.focus_mode,
        "mental_energy": str(snapshot.mental_energy),
        "physical_energy": str(snapshot.physical_energy),
    }
    log_event(
        logger,
        logging.INFO,
        "state patch task completed",
        event_id=event_id,
        focus_mode=snapshot.focus_mode,
        mental_energy=snapshot.mental_energy,
        physical_energy=snapshot.physical_energy,
    )
    return result
