"""Webhook routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id_from_request
from app.db.session import get_db_session
from app.schemas.webhooks import WebhookIngestResponse, WebhookSource
from app.services.event_ingestion import ingest_webhook_event_with_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{source}", response_model=WebhookIngestResponse, status_code=status.HTTP_200_OK)
def post_webhook(
    source: WebhookSource,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db_session),
) -> WebhookIngestResponse:
    """Accept a third-party webhook payload."""

    return ingest_webhook_event_with_db(db, get_request_id_from_request(request), source, payload)
