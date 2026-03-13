"""Background tasks related to event log compression."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.compress_event_logs")
def compress_event_logs() -> dict[str, str]:
    """Placeholder task for event log compression."""

    logger.info("compress_event_logs task queued")
    return {"status": "queued"}
