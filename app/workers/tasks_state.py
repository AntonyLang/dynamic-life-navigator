"""Background tasks related to state updates."""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.event_processing import apply_state_patch_from_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.apply_state_patch")
def apply_state_patch(event_id: str) -> dict[str, str]:
    """Apply a parsed event impact onto the current state snapshot."""

    logger.info("apply_state_patch task received event_id=%s", event_id)
    with SessionLocal() as session:
        snapshot = apply_state_patch_from_event(session, event_id)

    return {
        "status": "applied",
        "event_id": event_id,
        "focus_mode": snapshot.focus_mode,
        "mental_energy": str(snapshot.mental_energy),
        "physical_energy": str(snapshot.physical_energy),
    }
