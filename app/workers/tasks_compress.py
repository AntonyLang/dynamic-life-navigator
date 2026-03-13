"""Background tasks related to event log compression."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.event_compaction_service import compress_event_logs as compress_event_logs_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.compress_event_logs")
def compress_event_logs() -> dict[str, str]:
    """Compress old event logs without deleting fact records."""

    log_event(logger, logging.INFO, "event compression task started")
    with SessionLocal() as session:
        result = compress_event_logs_service(session)
    log_event(
        logger,
        logging.INFO,
        "event compression task completed",
        status=result.get("status"),
        compressed_count=result.get("compressed_count"),
    )
    return {"status": str(result["status"]), "compressed_count": str(result["compressed_count"])}
