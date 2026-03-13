"""Action node creation and profiling helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.action_node import ActionNode
from app.schemas.nodes import ActionNodeCreateRequest, ActionNodeCreateResponse, ActionNodeResponse
from app.services.node_profile_service import derive_node_profile
from app.workers.tasks_profile import profile_new_node

logger = logging.getLogger(__name__)
settings = get_settings()


def _serialize_node(node: ActionNode) -> ActionNodeResponse:
    return ActionNodeResponse(
        node_id=node.node_id,
        drive_type=node.drive_type,
        status=node.status,
        title=node.title,
        summary=node.summary,
        tags=node.tags,
        priority_score=node.priority_score,
        dynamic_urgency_score=node.dynamic_urgency_score,
        mental_energy_required=node.mental_energy_required,
        physical_energy_required=node.physical_energy_required,
        estimated_minutes=node.estimated_minutes,
        recommended_context_tags=node.recommended_context_tags,
        confidence_level=node.confidence_level,
        profiling_status=node.profiling_status,
        profiled_at=node.profiled_at,
    )


def _enqueue_profile_task(node_id: str) -> bool:
    """Queue async profiling without blocking creation."""

    if not settings.enable_worker_dispatch:
        log_event(logger, logging.INFO, "worker dispatch disabled; skipping node profile enqueue", node_id=node_id)
        return False

    try:
        profile_new_node.delay(node_id)
    except Exception:
        logger.exception("failed to enqueue node profile task node_id=%s", node_id)
        return False

    return True


def create_action_node(
    db: Session,
    request_id: str,
    payload: ActionNodeCreateRequest,
) -> ActionNodeCreateResponse:
    """Create a new action node with conservative defaults and async profiling."""

    initial_profile = derive_node_profile(payload.title, payload.tags, payload.summary)

    node = ActionNode(
        user_id=settings.default_user_id,
        drive_type=payload.drive_type,
        status="active",
        title=payload.title,
        summary=payload.summary,
        tags=payload.tags,
        priority_score=payload.priority_score if payload.priority_score is not None else 50,
        dynamic_urgency_score=payload.dynamic_urgency_score if payload.dynamic_urgency_score is not None else 0,
        mental_energy_required=initial_profile.mental_energy_required,
        physical_energy_required=initial_profile.physical_energy_required,
        estimated_minutes=payload.estimated_minutes if payload.estimated_minutes is not None else initial_profile.estimated_minutes,
        ddl_timestamp=payload.ddl_timestamp,
        recommended_context_tags=initial_profile.recommended_context_tags,
        confidence_level="low",
        profiling_status="pending",
        profiled_at=None,
        ai_context={},
        metadata_={"created_via": "api"},
        updated_at=datetime.now(timezone.utc),
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    profiling_enqueued = _enqueue_profile_task(str(node.node_id))
    log_event(
        logger,
        logging.INFO,
        "action node created",
        request_id=request_id,
        node_id=node.node_id,
        user_id=settings.default_user_id,
        drive_type=node.drive_type,
        profiling_status=node.profiling_status,
        profiling_enqueued=profiling_enqueued,
    )

    return ActionNodeCreateResponse(
        request_id=request_id,
        profiling_enqueued=profiling_enqueued,
        node=_serialize_node(node),
    )
