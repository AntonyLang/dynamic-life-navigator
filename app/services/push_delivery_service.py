"""Outbound push delivery service with webhook delivery audit."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.push_delivery_attempt import PushDeliveryAttempt
from app.models.recommendation_record import RecommendationRecord

logger = logging.getLogger(__name__)
WEBHOOK_SINK_CHANNEL = "webhook_sink"
RETRY_BACKOFF_SECONDS = (1, 2, 4)


def _build_delivery_items(recommendation: RecommendationRecord) -> list[dict[str, Any]]:
    rendered_items = recommendation.rendered_content.get("items", [])
    if not isinstance(rendered_items, list):
        return []

    items: list[dict[str, Any]] = []
    for item in rendered_items:
        if not isinstance(item, dict):
            continue
        node_id = item.get("node_id")
        title = item.get("title")
        message = item.get("message")
        reason_tags = item.get("reason_tags", [])
        items.append(
            {
                "node_id": str(node_id) if node_id is not None else "",
                "title": str(title) if title is not None else "",
                "message": str(message) if message is not None else "",
                "reason_tags": [str(tag) for tag in reason_tags] if isinstance(reason_tags, list) else [],
            }
        )
    return items


def build_push_webhook_payload(recommendation: RecommendationRecord) -> dict[str, Any]:
    """Build the stable webhook sink payload for one push recommendation."""

    return {
        "recommendation_id": str(recommendation.recommendation_id),
        "user_id": recommendation.user_id,
        "mode": recommendation.mode,
        "trigger_type": recommendation.trigger_type,
        "trigger_event_id": str(recommendation.trigger_event_id) if recommendation.trigger_event_id is not None else None,
        "created_at": recommendation.created_at.astimezone(timezone.utc).isoformat(),
        "items": _build_delivery_items(recommendation),
        "ranking_snapshot": recommendation.ranking_snapshot,
        "rendered_content": recommendation.rendered_content,
    }


def _render_response_payload(response: httpx.Response) -> dict[str, Any] | list[Any] | None:
    try:
        payload = response.json()
    except Exception:
        body_text = response.text.strip()
        return {"text": body_text[:2000]} if body_text else None

    if isinstance(payload, (dict, list)):
        return payload
    return {"value": payload}


def _record_attempt(
    db: Session,
    *,
    recommendation_id: UUID,
    attempt_number: int,
    delivery_status: str,
    target_ref: str | None,
    request_payload: dict[str, Any],
    response_status_code: int | None = None,
    response_payload: dict[str, Any] | list[Any] | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> PushDeliveryAttempt:
    attempt = PushDeliveryAttempt(
        recommendation_id=recommendation_id,
        channel=WEBHOOK_SINK_CHANNEL,
        attempt_number=attempt_number,
        delivery_status=delivery_status,
        target_ref=target_ref,
        request_payload=request_payload,
        response_status_code=response_status_code,
        response_payload=response_payload,
        error_code=error_code,
        error_detail=error_detail,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    return attempt


def _persist_terminal_status(
    db: Session,
    recommendation: RecommendationRecord,
    *,
    attempt_number: int,
    delivery_status: str,
    target_ref: str | None,
    request_payload: dict[str, Any],
    error_code: str | None = None,
    error_detail: str | None = None,
) -> dict[str, Any]:
    recommendation.delivery_status = delivery_status
    _record_attempt(
        db,
        recommendation_id=recommendation.recommendation_id,
        attempt_number=attempt_number,
        delivery_status=delivery_status,
        target_ref=target_ref,
        request_payload=request_payload,
        error_code=error_code,
        error_detail=error_detail,
    )
    db.add(recommendation)
    db.commit()
    log_event(
        logger,
        logging.INFO,
        "push delivery resolved without transport",
        recommendation_id=recommendation.recommendation_id,
        delivery_status=delivery_status,
        error_code=error_code,
    )
    return {
        "status": delivery_status,
        "recommendation_id": str(recommendation.recommendation_id),
        "attempt_count": attempt_number,
        "reason": error_code,
    }


def deliver_push_recommendation(
    db: Session,
    recommendation_id: UUID | str,
    *,
    sleep_fn=time.sleep,
) -> dict[str, Any]:
    """Deliver one generated push recommendation through the webhook sink."""

    recommendation = db.get(RecommendationRecord, recommendation_id)
    if recommendation is None:
        raise ValueError(f"recommendation {recommendation_id} not found")
    if recommendation.mode != "push" or recommendation.delivery_status != "generated":
        return {
            "status": "skipped",
            "recommendation_id": str(recommendation.recommendation_id),
            "attempt_count": 0,
            "reason": "not_generated_push",
        }

    settings = get_settings()
    request_payload = build_push_webhook_payload(recommendation)
    target_ref = settings.push_webhook_url

    if not settings.push_delivery_enabled:
        return _persist_terminal_status(
            db,
            recommendation,
            attempt_number=1,
            delivery_status="skipped",
            target_ref=target_ref,
            request_payload=request_payload,
            error_code="delivery_disabled",
            error_detail="push delivery is disabled by configuration",
        )

    if settings.push_delivery_channel != WEBHOOK_SINK_CHANNEL:
        return _persist_terminal_status(
            db,
            recommendation,
            attempt_number=1,
            delivery_status="skipped",
            target_ref=target_ref,
            request_payload=request_payload,
            error_code="unsupported_channel",
            error_detail=f"unsupported push delivery channel: {settings.push_delivery_channel}",
        )

    if not target_ref:
        return _persist_terminal_status(
            db,
            recommendation,
            attempt_number=1,
            delivery_status="skipped",
            target_ref=None,
            request_payload=request_payload,
            error_code="missing_webhook_url",
            error_detail="push webhook URL is not configured",
        )

    max_attempts = settings.push_delivery_max_attempts
    request_body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last_error_code = "delivery_failed"
    last_error_detail: str | None = None

    for attempt_number in range(1, max_attempts + 1):
        request_id = str(uuid4())
        try:
            with httpx.Client(timeout=settings.push_webhook_timeout_seconds, trust_env=False) as client:
                response = client.post(
                    target_ref,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "X-Recommendation-Id": str(recommendation.recommendation_id),
                        "X-Request-Id": request_id,
                    },
                    content=request_body,
                )
        except httpx.HTTPError as exc:
            last_error_code = exc.__class__.__name__
            last_error_detail = str(exc)[:1000]
            _record_attempt(
                db,
                recommendation_id=recommendation.recommendation_id,
                attempt_number=attempt_number,
                delivery_status="failed",
                target_ref=target_ref,
                request_payload=request_payload,
                error_code=last_error_code,
                error_detail=last_error_detail,
            )
            db.commit()
        else:
            response_payload = _render_response_payload(response)
            if 200 <= response.status_code < 300:
                recommendation.delivery_status = "sent"
                _record_attempt(
                    db,
                    recommendation_id=recommendation.recommendation_id,
                    attempt_number=attempt_number,
                    delivery_status="sent",
                    target_ref=target_ref,
                    request_payload=request_payload,
                    response_status_code=response.status_code,
                    response_payload=response_payload,
                )
                db.add(recommendation)
                db.commit()
                log_event(
                    logger,
                    logging.INFO,
                    "push delivery sent",
                    recommendation_id=recommendation.recommendation_id,
                    attempt_number=attempt_number,
                    target_ref=target_ref,
                    request_id=request_id,
                )
                return {
                    "status": "sent",
                    "recommendation_id": str(recommendation.recommendation_id),
                    "attempt_count": attempt_number,
                    "reason": None,
                }

            last_error_code = f"http_status_{response.status_code}"
            body_text = response.text.strip()
            last_error_detail = body_text[:1000] if body_text else None
            _record_attempt(
                db,
                recommendation_id=recommendation.recommendation_id,
                attempt_number=attempt_number,
                delivery_status="failed",
                target_ref=target_ref,
                request_payload=request_payload,
                response_status_code=response.status_code,
                response_payload=response_payload,
                error_code=last_error_code,
                error_detail=last_error_detail,
            )
            db.commit()

        if attempt_number < max_attempts:
            sleep_fn(RETRY_BACKOFF_SECONDS[min(attempt_number - 1, len(RETRY_BACKOFF_SECONDS) - 1)])

    recommendation.delivery_status = "failed"
    db.add(recommendation)
    db.commit()
    log_event(
        logger,
        logging.WARNING,
        "push delivery failed",
        recommendation_id=recommendation.recommendation_id,
        attempt_count=max_attempts,
        error_code=last_error_code,
    )
    return {
        "status": "failed",
        "recommendation_id": str(recommendation.recommendation_id),
        "attempt_count": max_attempts,
        "reason": last_error_code,
        "error_detail": last_error_detail,
    }
