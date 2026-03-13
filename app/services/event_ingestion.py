"""Event ingestion service implementation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.schemas.webhooks import WebhookIngestResponse
from app.services.state_service import get_current_state
from app.workers.tasks_parse import parse_event_log

logger = logging.getLogger(__name__)
settings = get_settings()


def _enqueue_parse_task(event_id: str) -> None:
    """Attempt to enqueue parse work without making the request path brittle."""

    if not settings.enable_worker_dispatch:
        logger.info("worker dispatch disabled; skipping parse_event_log enqueue for event_id=%s", event_id)
        return

    try:
        parse_event_log.delay(event_id)
    except Exception:
        logger.exception("failed to enqueue parse_event_log for event_id=%s", event_id)


def ingest_chat_message(db: Session, request_id: str, payload: ChatMessageRequest) -> ChatMessageResponse:
    """Persist a raw chat event and return an ack-style response."""

    event_id = uuid4()
    payload_hash = sha256(f"{payload.channel}|{payload.client_message_id}|{payload.text}".encode("utf-8")).hexdigest()

    event_log = EventLog(
        event_id=event_id,
        user_id=settings.default_user_id,
        source=payload.channel,
        source_event_type=payload.message_type,
        external_event_id=payload.client_message_id,
        payload_hash=payload_hash,
        raw_text=payload.text,
        raw_payload={
            "channel": payload.channel,
            "message_type": payload.message_type,
            "text": payload.text,
            "client_message_id": payload.client_message_id,
        },
        parse_status="pending",
        processed_status="new",
        occurred_at=payload.occurred_at,
        ingested_at=datetime.now(timezone.utc),
    )
    db.add(event_log)
    db.commit()

    _enqueue_parse_task(str(event_id))
    current_state = get_current_state(db)

    return ChatMessageResponse(
        request_id=request_id,
        event_id=event_id,
        state=current_state,
        assistant_reply="Recorded. I am updating your state now.",
        suggest_next_action=False,
        accepted=True,
        processing=True,
    )


def ingest_webhook_event(request_id: str) -> WebhookIngestResponse:
    """Return a placeholder webhook ack response."""

    raise RuntimeError("ingest_webhook_event requires a database session")


def ingest_webhook_event_with_db(
    db: Session,
    request_id: str,
    source: str,
    payload: dict,
) -> WebhookIngestResponse:
    """Persist a raw webhook payload and return an idempotent ack."""

    event_id = uuid4()
    external_event_id = payload.get("external_event_id") or payload.get("event_id") or payload.get("id")
    payload_hash = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    event_log = EventLog(
        event_id=event_id,
        user_id=settings.default_user_id,
        source=source,
        source_event_type=payload.get("type") if isinstance(payload.get("type"), str) else None,
        external_event_id=str(external_event_id) if external_event_id is not None else None,
        payload_hash=payload_hash,
        raw_payload=payload,
        parse_status="pending",
        processed_status="new",
        occurred_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
        source_sequence=str(payload.get("sequence")) if payload.get("sequence") is not None else None,
    )

    try:
        db.add(event_log)
        db.commit()
        duplicate = False
    except IntegrityError:
        db.rollback()
        duplicate = True

        if external_event_id is not None:
            existing_event_id = db.scalar(
                select(EventLog.event_id)
                .where(
                    EventLog.source == source,
                    EventLog.external_event_id == str(external_event_id),
                )
                .order_by(EventLog.created_at.desc())
                .limit(1)
            )
        else:
            existing_event_id = db.scalar(
                select(EventLog.event_id)
                .where(
                    EventLog.source == source,
                    EventLog.payload_hash == payload_hash,
                )
                .order_by(EventLog.created_at.desc())
                .limit(1)
            )

        if existing_event_id is not None:
            event_id = existing_event_id

    if not duplicate:
        _enqueue_parse_task(str(event_id))

    return WebhookIngestResponse(
        request_id=request_id,
        accepted=True,
        duplicate=duplicate,
        event_id=event_id,
    )
