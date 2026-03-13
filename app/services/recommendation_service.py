"""Recommendation service implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation
from app.models.user_state import UserState
from app.models.recommendation_record import RecommendationRecord
from app.schemas.common import RecommendationItem
from app.schemas.recommendations import RecommendationPullResponse
from app.services.state_service import _ensure_user_state

settings = get_settings()
RECENT_REJECTION_WINDOW = timedelta(days=3)


@dataclass(slots=True)
class CandidateScore:
    node: ActionNode
    score: int
    reason_tags: list[str]


def _fallback_message() -> str:
    return "No strong recommendation yet. Try a 10-minute low-effort task, or ask for something short and light."


def _latest_annotation_expiry(db: Session) -> dict:
    rows = db.execute(
        select(
            NodeAnnotation.node_id,
            func.max(NodeAnnotation.expires_at).label("latest_expires_at"),
        ).group_by(NodeAnnotation.node_id)
    ).all()
    return {node_id: latest_expires_at for node_id, latest_expires_at in rows}


def _is_on_cooldown(node: ActionNode, now: datetime) -> bool:
    if node.last_recommended_at is None:
        return False
    return node.last_recommended_at + timedelta(hours=node.cooldown_hours) > now


def _score_node(node: ActionNode, state: UserState, latest_expires_at: datetime | None, now: datetime) -> CandidateScore | None:
    """Apply conservative filtering and ranking for pull recommendations."""

    if state.mental_energy + 10 < node.mental_energy_required:
        return None
    if state.physical_energy + 10 < node.physical_energy_required:
        return None
    if _is_on_cooldown(node, now):
        return None

    score = 0
    reason_tags: list[str] = []

    score += node.priority_score
    score += node.dynamic_urgency_score

    mental_fit = max(0, 30 - max(0, node.mental_energy_required - state.mental_energy))
    physical_fit = max(0, 30 - max(0, node.physical_energy_required - state.physical_energy))
    score += mental_fit + physical_fit
    reason_tags.append("state_match")

    if node.ddl_timestamp is not None and node.ddl_timestamp <= now + timedelta(days=2):
        score += 25
        reason_tags.append("ddl_urgent")

    if latest_expires_at is not None and latest_expires_at > now:
        score += 10
        reason_tags.append("fresh_annotation")

    if node.last_rejected_at is not None and node.last_rejected_at >= now - RECENT_REJECTION_WINDOW:
        score -= 35
        reason_tags.append("recent_rejection_penalty")

    if node.confidence_level == "high":
        score += 8
    elif node.confidence_level == "medium":
        score += 4

    return CandidateScore(node=node, score=score, reason_tags=reason_tags)


def _build_message(node: ActionNode, reason_tags: list[str]) -> str:
    if "ddl_urgent" in reason_tags:
        return f"{node.title} is time-sensitive. Do the smallest concrete step next."
    if "fresh_annotation" in reason_tags:
        return f"{node.title} matches your current state and has fresh context ready."
    return f"{node.title} is the lightest viable next step for your current state."


def get_pull_recommendations(
    db: Session,
    request_id: str,
    *,
    limit: int = 2,
) -> RecommendationPullResponse:
    """Persist a pull recommendation record and return ranked candidates."""

    now = datetime.now(timezone.utc)
    state = _ensure_user_state(db)
    latest_annotation_expiry = _latest_annotation_expiry(db)
    active_nodes = db.scalars(
        select(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
        )
    ).all()

    scored_candidates = []
    for node in active_nodes:
        candidate = _score_node(node, state, latest_annotation_expiry.get(node.node_id), now)
        if candidate is not None:
            scored_candidates.append(candidate)

    scored_candidates.sort(key=lambda candidate: (candidate.score, candidate.node.updated_at), reverse=True)
    candidate_node_ids = [candidate.node.node_id for candidate in scored_candidates]
    selected_candidates = scored_candidates[:limit]
    selected_node_ids = [candidate.node.node_id for candidate in selected_candidates]

    ranking_snapshot = {
        str(candidate.node.node_id): {
            "score": candidate.score,
            "reason_tags": candidate.reason_tags,
        }
        for candidate in scored_candidates
    }

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
            message=_build_message(candidate.node, candidate.reason_tags),
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

    return RecommendationPullResponse(
        request_id=request_id,
        recommendation_id=recommendation.recommendation_id,
        mode="pull",
        items=items,
        empty_state=False,
        fallback_message=None,
    )
