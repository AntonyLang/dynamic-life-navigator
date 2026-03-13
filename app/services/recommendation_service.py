"""Recommendation service implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.recommendation_record import RecommendationRecord
from app.schemas.common import RecommendationItem
from app.schemas.recommendations import RecommendationPullResponse
from app.ranking import build_recommendation_message, get_ranked_candidates

settings = get_settings()
logger = logging.getLogger(__name__)


def _fallback_message() -> str:
    return "No strong recommendation yet. Try a 10-minute low-effort task, or ask for something short and light."


def get_pull_recommendations(
    db: Session,
    request_id: str,
    *,
    limit: int = 2,
) -> RecommendationPullResponse:
    """Persist a pull recommendation record and return ranked candidates."""

    now = datetime.now(timezone.utc)
    _, scored_candidates, ranking_snapshot = get_ranked_candidates(db, now=now)
    candidate_node_ids = [candidate.node.node_id for candidate in scored_candidates]
    selected_candidates = scored_candidates[:limit]
    selected_node_ids = [candidate.node.node_id for candidate in selected_candidates]

    if not selected_candidates:
        fallback_message = _fallback_message()
        recommendation = RecommendationRecord(
            user_id=settings.default_user_id,
            mode="pull",
            trigger_type="manual_pull",
            candidate_node_ids=[],
            selected_node_ids=[],
            ranking_snapshot=ranking_snapshot,
            rendered_content={"fallback_message": fallback_message, "items": []},
            delivery_status="generated",
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        log_event(
            logger,
            logging.INFO,
            "pull recommendation generated",
            recommendation_id=recommendation.recommendation_id,
            user_id=settings.default_user_id,
            mode="pull",
            empty_state=True,
            candidate_count=len(scored_candidates),
        )

        return RecommendationPullResponse(
            request_id=request_id,
            recommendation_id=recommendation.recommendation_id,
            mode="pull",
            items=[],
            empty_state=True,
            fallback_message=fallback_message,
        )

    items = [
        RecommendationItem(
            node_id=candidate.node.node_id,
            title=candidate.node.title,
            message=build_recommendation_message(candidate.node, candidate.reason_tags),
            reason_tags=candidate.reason_tags,
        )
        for candidate in selected_candidates
    ]

    recommendation = RecommendationRecord(
        user_id=settings.default_user_id,
        mode="pull",
        trigger_type="manual_pull",
        candidate_node_ids=candidate_node_ids,
        selected_node_ids=selected_node_ids,
        ranking_snapshot=ranking_snapshot,
        rendered_content={
            "fallback_message": None,
            "items": [item.model_dump(mode="json") for item in items],
        },
        delivery_status="generated",
    )
    db.add(recommendation)

    for candidate in selected_candidates:
        candidate.node.last_recommended_at = now
        db.add(candidate.node)

    db.commit()
    db.refresh(recommendation)
    log_event(
        logger,
        logging.INFO,
        "pull recommendation generated",
        recommendation_id=recommendation.recommendation_id,
        user_id=settings.default_user_id,
        mode="pull",
        empty_state=False,
        candidate_count=len(scored_candidates),
        selected_count=len(selected_candidates),
    )

    return RecommendationPullResponse(
        request_id=request_id,
        recommendation_id=recommendation.recommendation_id,
        mode="pull",
        items=items,
        empty_state=False,
        fallback_message=None,
    )
