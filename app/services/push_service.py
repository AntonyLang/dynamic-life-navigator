"""Push recommendation evaluation service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.recommendation_record import RecommendationRecord
from app.ranking import CandidateScore, build_recommendation_message, get_ranked_candidates

settings = get_settings()
logger = logging.getLogger(__name__)
PUSH_SCORE_THRESHOLD = 150
PUSH_REPEAT_WINDOW = timedelta(hours=12)


def _recent_push_exists(db: Session, node_id: UUID, now: datetime) -> bool:
    """Return whether the node was already pushed recently."""

    recent_push = db.scalar(
        select(RecommendationRecord.recommendation_id)
        .where(
            RecommendationRecord.user_id == settings.default_user_id,
            RecommendationRecord.mode == "push",
            RecommendationRecord.created_at >= now - PUSH_REPEAT_WINDOW,
            RecommendationRecord.selected_node_ids.any(node_id),
        )
        .limit(1)
    )
    return recent_push is not None


def _persist_skipped_push(
    db: Session,
    *,
    trigger_event_id: UUID | str | None,
    ranking_snapshot: dict[str, dict],
    reason: str,
) -> RecommendationRecord:
    recommendation = RecommendationRecord(
        user_id=settings.default_user_id,
        mode="push",
        trigger_type="state_change",
        trigger_event_id=trigger_event_id,
        candidate_node_ids=[],
        selected_node_ids=[],
        ranking_snapshot=ranking_snapshot,
        rendered_content={"fallback_message": None, "items": [], "skip_reason": reason},
        delivery_status="skipped",
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    log_event(
        logger,
        logging.INFO,
        "push recommendation evaluated",
        recommendation_id=recommendation.recommendation_id,
        trigger_event_id=trigger_event_id,
        user_id=settings.default_user_id,
        mode="push",
        delivery_status="skipped",
        skip_reason=reason,
    )
    return recommendation


def evaluate_push_opportunities(db: Session, trigger_event_id: UUID | str | None = None) -> dict[str, str | None]:
    """Evaluate whether a weak push recommendation should be generated."""

    now = datetime.now(timezone.utc)
    state, ranked_candidates, ranking_snapshot = get_ranked_candidates(db, now=now)

    if state.do_not_disturb_until is not None and state.do_not_disturb_until > now:
        recommendation = _persist_skipped_push(
            db,
            trigger_event_id=trigger_event_id,
            ranking_snapshot=ranking_snapshot,
            reason="do_not_disturb",
        )
        return {
            "status": "skipped",
            "recommendation_id": str(recommendation.recommendation_id),
            "trigger_event_id": str(trigger_event_id) if trigger_event_id is not None else None,
            "reason": "do_not_disturb",
        }

    if not ranked_candidates:
        recommendation = _persist_skipped_push(
            db,
            trigger_event_id=trigger_event_id,
            ranking_snapshot=ranking_snapshot,
            reason="no_candidate",
        )
        return {
            "status": "skipped",
            "recommendation_id": str(recommendation.recommendation_id),
            "trigger_event_id": str(trigger_event_id) if trigger_event_id is not None else None,
            "reason": "no_candidate",
        }

    selected_candidate: CandidateScore | None = None
    skip_reason = "below_threshold"
    for candidate in ranked_candidates:
        if candidate.score < PUSH_SCORE_THRESHOLD:
            break
        if _recent_push_exists(db, candidate.node.node_id, now):
            skip_reason = "recent_push_repeat"
            continue
        selected_candidate = candidate
        break

    if selected_candidate is None:
        recommendation = _persist_skipped_push(
            db,
            trigger_event_id=trigger_event_id,
            ranking_snapshot=ranking_snapshot,
            reason=skip_reason,
        )
        return {
            "status": "skipped",
            "recommendation_id": str(recommendation.recommendation_id),
            "trigger_event_id": str(trigger_event_id) if trigger_event_id is not None else None,
            "reason": skip_reason,
        }

    recommendation = RecommendationRecord(
        user_id=settings.default_user_id,
        mode="push",
        trigger_type="state_change",
        trigger_event_id=trigger_event_id,
        candidate_node_ids=[candidate.node.node_id for candidate in ranked_candidates],
        selected_node_ids=[selected_candidate.node.node_id],
        ranking_snapshot=ranking_snapshot,
        rendered_content={
            "fallback_message": None,
            "items": [
                {
                    "node_id": str(selected_candidate.node.node_id),
                    "title": selected_candidate.node.title,
                    "message": build_recommendation_message(selected_candidate.node, selected_candidate.reason_tags),
                    "reason_tags": selected_candidate.reason_tags,
                }
            ],
        },
        delivery_status="generated",
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    log_event(
        logger,
        logging.INFO,
        "push recommendation evaluated",
        recommendation_id=recommendation.recommendation_id,
        trigger_event_id=trigger_event_id,
        user_id=settings.default_user_id,
        mode="push",
        delivery_status="generated",
        selected_count=1,
    )

    return {
        "status": "generated",
        "recommendation_id": str(recommendation.recommendation_id),
        "trigger_event_id": str(trigger_event_id) if trigger_event_id is not None else None,
        "reason": None,
    }
