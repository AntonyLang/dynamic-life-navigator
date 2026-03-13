"""Feedback service implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.schemas.recommendations import RecommendationFeedbackRequest, RecommendationFeedbackResponse

settings = get_settings()


def _resolve_feedback_node(
    db: Session,
    recommendation: RecommendationRecord,
    payload: RecommendationFeedbackRequest,
) -> ActionNode | None:
    """Resolve and validate the node targeted by this feedback."""

    target_node_id = payload.node_id
    if target_node_id is None and len(recommendation.selected_node_ids) == 1:
        target_node_id = recommendation.selected_node_ids[0]

    if target_node_id is None:
        return None

    allowed_node_ids = set(recommendation.selected_node_ids) | set(recommendation.candidate_node_ids)
    if target_node_id not in allowed_node_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"node {target_node_id} is not part of recommendation {recommendation.recommendation_id}",
        )

    node = db.get(ActionNode, target_node_id)
    if node is None or node.user_id != settings.default_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"node {target_node_id} not found",
        )

    return node


def _apply_feedback_to_node(node: ActionNode | None, feedback: str, now: datetime) -> None:
    """Project user feedback back onto node-level ranking signals."""

    if node is None:
        return

    if feedback == "accepted":
        node.last_completed_at = now
        node.last_rejected_at = None
    elif feedback in {"dismissed", "rejected"}:
        node.last_rejected_at = now
    elif feedback == "snoozed":
        node.last_recommended_at = now

    node.updated_at = now


def submit_feedback(
    db: Session,
    request_id: str,
    recommendation_id: UUID,
    payload: RecommendationFeedbackRequest,
) -> RecommendationFeedbackResponse:
    """Persist user feedback for an existing recommendation."""

    recommendation = db.get(RecommendationRecord, recommendation_id)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {recommendation_id} not found",
        )

    now = datetime.now(timezone.utc)
    node = _resolve_feedback_node(db, recommendation, payload)

    feedback = RecommendationFeedback(
        recommendation_id=recommendation_id,
        user_id=settings.default_user_id,
        node_id=node.node_id if node is not None else payload.node_id,
        feedback=payload.feedback,
        channel=payload.channel,
    )
    db.add(feedback)
    _apply_feedback_to_node(node, payload.feedback, now)
    if node is not None:
        db.add(node)
    db.commit()

    return RecommendationFeedbackResponse(
        request_id=request_id,
        recommendation_id=recommendation_id,
        accepted=True,
        feedback=payload.feedback,
    )
