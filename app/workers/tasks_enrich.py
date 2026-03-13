"""Background tasks related to node enrichment."""

from __future__ import annotations

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.enrich_active_nodes")
def enrich_active_nodes() -> dict[str, str]:
    """Placeholder task for annotation enrichment."""

    logger.info("enrich_active_nodes task queued")
    return {"status": "queued"}
