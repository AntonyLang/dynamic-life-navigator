"""Event ingestion service implementation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.idempotency import claim_webhook_idempotency
from app.core.logging import log_event
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
        log_event(logger, logging.INFO, "worker dispatch disabled; skipping parse enqueue", event_id=event_id)
        return

    try:
        parse_event_log.delay(event_id)
    except Exception:
        logger.exception("failed to enqueue parse task event_id=%s", event_id)


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
    try:
        db.add(event_log)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        log_event(
            logger,
            logging.INFO,
            "chat duplicate suppressed",
            user_id=settings.default_user_id,
            source=payload.channel,
            duplicate=True,
            external_event_id=payload.client_message_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="client_message_id already exists for this source",
        ) from exc

    log_event(
        logger,
        logging.INFO,
        "chat event ingested",
        event_id=event_id,
        user_id=settings.default_user_id,
        source=payload.channel,
        parse_status="pending",
    )

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


def _find_existing_webhook_event_id(
    db: Session,
    *,
    source: str,
    external_event_id: str | None,
    payload_hash: str,
):
    if external_event_id is not None:
        return db.scalar(
            select(EventLog.event_id)
            .where(
                EventLog.source == source,
                EventLog.external_event_id == external_event_id,
            )
            .order_by(EventLog.created_at.desc())
            .limit(1)
        )

    return db.scalar(
        select(EventLog.event_id)
        .where(
            EventLog.source == source,
            EventLog.payload_hash == payload_hash,
        )
        .order_by(EventLog.created_at.desc())
        .limit(1)
    )


def _build_webhook_idempotency_key(
    *,
    user_id: str,
    source: str,
    external_event_id: str | None,
    payload_hash: str,
) -> str:
    identifier = external_event_id or payload_hash
    return f"idempotency:{user_id}:{source}:{identifier}"


def _parse_top_level_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=timezone.utc)

    if isinstance(raw_value, (int, float)):
        timestamp = float(raw_value)
    elif isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if not trimmed:
            return None
        if trimmed.isdigit():
            timestamp = float(trimmed)
        else:
            normalized = trimmed.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    else:
        return None

    if timestamp > 1_000_000_000_000:
        timestamp /= 1000.0
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _derive_webhook_occurred_at(payload: dict[str, Any], now: datetime) -> datetime:
    for field_name in ("occurred_at", "event_time", "timestamp", "created_at", "start_time", "updated_at"):
        parsed = _parse_top_level_datetime(payload.get(field_name))
        if parsed is not None:
            return parsed
    return now


def ingest_webhook_event_with_db(
    db: Session,
    request_id: str,
    source: str,
    payload: dict,
) -> WebhookIngestResponse:
    """Persist a raw webhook payload and return an idempotent ack."""

    event_id = uuid4()
    now = datetime.now(timezone.utc)
    external_event_id = payload.get("external_event_id") or payload.get("event_id") or payload.get("id")
    payload_hash = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    external_event_id_str = str(external_event_id) if external_event_id is not None else None
    idempotency_key = _build_webhook_idempotency_key(
        user_id=settings.default_user_id,
        source=source,
        external_event_id=external_event_id_str,
        payload_hash=payload_hash,
    )
    should_continue_to_db = claim_webhook_idempotency(
        idempotency_key,
        settings.webhook_idempotency_ttl_seconds,
    )

    if not should_continue_to_db:
        existing_event_id = _find_existing_webhook_event_id(
            db,
            source=source,
            external_event_id=external_event_id_str,
            payload_hash=payload_hash,
        )
        if existing_event_id is not None:
            log_event(
                logger,
                logging.INFO,
                "webhook duplicate suppressed by redis idempotency",
                event_id=existing_event_id,
                user_id=settings.default_user_id,
                source=source,
                duplicate=True,
            )
            return WebhookIngestResponse(
                request_id=request_id,
                accepted=True,
                duplicate=True,
                event_id=existing_event_id,
            )

    event_log = EventLog(
        event_id=event_id,
        user_id=settings.default_user_id,
        source=source,
        source_event_type=payload.get("type") if isinstance(payload.get("type"), str) else None,
        external_event_id=external_event_id_str,
        payload_hash=payload_hash,
        raw_payload=payload,
        parse_status="pending",
        processed_status="new",
        occurred_at=_derive_webhook_occurred_at(payload, now),
        ingested_at=now,
        source_sequence=str(payload.get("sequence")) if payload.get("sequence") is not None else None,
    )

    try:
        db.add(event_log)
        db.commit()
        duplicate = False
        log_event(
            logger,
            logging.INFO,
            "webhook event ingested",
            event_id=event_id,
            user_id=settings.default_user_id,
            source=source,
            duplicate=False,
            parse_status="pending",
        )
    except IntegrityError:
        db.rollback()
        duplicate = True
        existing_event_id = _find_existing_webhook_event_id(
            db,
            source=source,
            external_event_id=external_event_id_str,
            payload_hash=payload_hash,
        )

        if existing_event_id is not None:
            event_id = existing_event_id
        log_event(
            logger,
            logging.INFO,
            "webhook duplicate suppressed",
            event_id=event_id,
            user_id=settings.default_user_id,
            source=source,
            duplicate=True,
        )

    if not duplicate:
        _enqueue_parse_task(str(event_id))

    return WebhookIngestResponse(
        request_id=request_id,
        accepted=True,
        duplicate=duplicate,
        event_id=event_id,
    )
