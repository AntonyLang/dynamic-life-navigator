"""Recommendation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.recommendations import (
    RecommendationBriefResponse,
    RecommendationFeedbackRequest,
    RecommendationFeedbackResponse,
    RecommendationPullResponse,
)
from app.services.brief_service import get_brief
from app.services.feedback_service import submit_feedback
from app.services.recommendation_service import get_pull_recommendations
from app.services.request_context import get_request_id_from_request

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/pull", response_model=RecommendationPullResponse, status_code=status.HTTP_200_OK)
def get_recommendations_pull(
    request: Request,
    limit: int = Query(default=2, ge=1, le=3),
    include_debug: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> RecommendationPullResponse:
    """Return pull recommendations for the current state."""

    _ = include_debug
    return get_pull_recommendations(db, get_request_id_from_request(request), limit=limit)


@router.get("/brief", response_model=RecommendationBriefResponse, status_code=status.HTTP_200_OK)
def get_recommendations_brief(
    request: Request,
    db: Session = Depends(get_db_session),
) -> RecommendationBriefResponse:
    """Return a brief summary of current active nodes."""

    return get_brief(db, get_request_id_from_request(request))


@router.post("/{recommendation_id}/feedback", response_model=RecommendationFeedbackResponse, status_code=status.HTTP_200_OK)
def post_recommendation_feedback(
    recommendation_id: UUID,
    payload: RecommendationFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> RecommendationFeedbackResponse:
    """Accept user feedback for a recommendation."""

    return submit_feedback(db, get_request_id_from_request(request), recommendation_id, payload)
