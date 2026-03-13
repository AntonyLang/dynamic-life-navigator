"""Background tasks related to node enrichment."""

from __future__ import annotations

import logging

from app.core.logging import log_event
from app.db.session import SessionLocal
from app.services.annotation_service import enrich_active_nodes as enrich_active_nodes_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.enrich_active_nodes")
def enrich_active_nodes() -> dict[str, str]:
    """Refresh lightweight annotations for active nodes."""

    log_event(logger, logging.INFO, "node enrichment task started")
    with SessionLocal() as session:
        result = enrich_active_nodes_service(session)
    log_event(
        logger,
        logging.INFO,
        "node enrichment task completed",
        status=result.get("status"),
        enriched_count=result.get("enriched_count"),
    )
    return {"status": str(result["status"]), "enriched_count": str(result["enriched_count"])}
