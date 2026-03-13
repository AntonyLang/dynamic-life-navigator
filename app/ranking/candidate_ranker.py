"""Candidate filtering and ranking helpers.

The current MVP intentionally keeps a +10 energy tolerance buffer when
matching node requirements against the current state. This is a deliberate
product tuning choice, not accidental drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.models.user_state import UserState
from app.services.state_service import _ensure_user_state

settings = get_settings()
RECENT_REJECTION_WINDOW = timedelta(days=3)
RECENT_COMPLETION_WINDOW = timedelta(days=1)
RECENT_EXPOSURE_WINDOW = timedelta(days=7)
ENERGY_MATCH_TOLERANCE = 10


@dataclass(slots=True)
class CandidateScore:
    node: ActionNode
    score: int
    reason_tags: list[str]
    breakdown: dict[str, int]


def build_recommendation_message(node: ActionNode, reason_tags: list[str]) -> str:
    """Render the lightweight deterministic recommendation message."""

    if "ddl_urgent" in reason_tags:
        return f"{node.title} is time-sensitive. Do the smallest concrete step next."
    if "fresh_annotation" in reason_tags:
        return f"{node.title} matches your current state and has fresh context ready."
    return f"{node.title} is the lightest viable next step for your current state."


def _latest_annotation_expiry(db: Session) -> dict[UUID, datetime | None]:
    rows = db.execute(
        select(
            NodeAnnotation.node_id,
            func.max(NodeAnnotation.expires_at).label("latest_expires_at"),
        ).group_by(NodeAnnotation.node_id)
    ).all()
    return {node_id: latest_expires_at for node_id, latest_expires_at in rows}


def _recent_unaccepted_exposure_counts(db: Session, now: datetime) -> dict[UUID, int]:
    """Count recent exposures that did not receive accepted feedback."""

    recommendation_records = db.scalars(
        select(RecommendationRecord).where(
            RecommendationRecord.user_id == settings.default_user_id,
            RecommendationRecord.mode == "pull",
            RecommendationRecord.created_at >= now - RECENT_EXPOSURE_WINDOW,
        )
    ).all()

    if not recommendation_records:
        return {}

    recommendation_ids = [record.recommendation_id for record in recommendation_records]
    accepted_feedback = db.execute(
        select(
            RecommendationFeedback.recommendation_id,
            RecommendationFeedback.node_id,
        ).where(
            RecommendationFeedback.recommendation_id.in_(recommendation_ids),
            RecommendationFeedback.feedback == "accepted",
            RecommendationFeedback.node_id.is_not(None),
        )
    ).all()
    accepted_pairs = {(recommendation_id, node_id) for recommendation_id, node_id in accepted_feedback}

    counts: dict[UUID, int] = {}
    for record in recommendation_records:
        for node_id in record.selected_node_ids:
            if (record.recommendation_id, node_id) not in accepted_pairs:
                counts[node_id] = counts.get(node_id, 0) + 1

    return counts


def _is_on_cooldown(node: ActionNode, now: datetime) -> bool:
    if node.last_recommended_at is None:
        return False
    return node.last_recommended_at + timedelta(hours=node.cooldown_hours) > now


def _has_recent_same_type_completion(node: ActionNode, active_nodes: list[ActionNode], now: datetime) -> bool:
    """Check whether a sibling node of the same broad type was completed recently."""

    node_tags = set(node.tags)
    for other_node in active_nodes:
        if other_node.node_id == node.node_id:
            continue
        if other_node.last_completed_at is None or other_node.last_completed_at < now - RECENT_COMPLETION_WINDOW:
            continue
        if other_node.drive_type != node.drive_type:
            continue

        other_tags = set(other_node.tags)
        if not node_tags or not other_tags or node_tags.intersection(other_tags):
            return True

    return False


def _score_node(
    node: ActionNode,
    state: UserState,
    latest_expires_at: datetime | None,
    recent_exposure_counts: dict[UUID, int],
    active_nodes: list[ActionNode],
    now: datetime,
) -> CandidateScore | None:
    """Apply conservative filtering and ranking for recommendations."""

    if state.mental_energy + ENERGY_MATCH_TOLERANCE < node.mental_energy_required:
        return None
    if state.physical_energy + ENERGY_MATCH_TOLERANCE < node.physical_energy_required:
        return None
    if _is_on_cooldown(node, now):
        return None

    score = 0
    reason_tags: list[str] = []
    breakdown: dict[str, int] = {}

    breakdown["priority_score"] = node.priority_score
    breakdown["dynamic_urgency_score"] = node.dynamic_urgency_score
    score += node.priority_score + node.dynamic_urgency_score

    mental_fit = max(0, 30 - max(0, node.mental_energy_required - state.mental_energy))
    physical_fit = max(0, 30 - max(0, node.physical_energy_required - state.physical_energy))
    breakdown["state_fit_bonus"] = mental_fit + physical_fit
    score += breakdown["state_fit_bonus"]
    reason_tags.append("state_match")

    if node.ddl_timestamp is not None and node.ddl_timestamp <= now + timedelta(days=2):
        breakdown["ddl_urgent_bonus"] = 25
        score += 25
        reason_tags.append("ddl_urgent")

    if latest_expires_at is not None and latest_expires_at > now:
        breakdown["fresh_annotation_bonus"] = 10
        score += 10
        reason_tags.append("fresh_annotation")

    if node.last_rejected_at is not None and node.last_rejected_at >= now - RECENT_REJECTION_WINDOW:
        breakdown["recent_rejection_penalty"] = -35
        score -= 35
        reason_tags.append("recent_rejection_penalty")

    if node.last_completed_at is not None and node.last_completed_at >= now - RECENT_COMPLETION_WINDOW:
        breakdown["recent_completion_penalty"] = -40
        score -= 40
        reason_tags.append("recent_completion_penalty")
    elif _has_recent_same_type_completion(node, active_nodes, now):
        breakdown["same_type_recent_completion_penalty"] = -20
        score -= 20
        reason_tags.append("same_type_recent_completion_penalty")

    recent_exposures = recent_exposure_counts.get(node.node_id, 0)
    if recent_exposures >= 2:
        exposure_penalty = min(36, recent_exposures * 12)
        breakdown["exposure_fatigue_penalty"] = -exposure_penalty
        score -= exposure_penalty
        reason_tags.append("exposure_fatigue_penalty")

    if node.confidence_level == "high":
        breakdown["confidence_bonus"] = 8
        score += 8
    elif node.confidence_level == "medium":
        breakdown["confidence_bonus"] = 4
        score += 4

    breakdown["final_score"] = score
    return CandidateScore(node=node, score=score, reason_tags=reason_tags, breakdown=breakdown)


def get_ranked_candidates(
    db: Session,
    *,
    now: datetime | None = None,
) -> tuple[UserState, list[CandidateScore], dict[str, dict]]:
    """Return the current state, scored candidates, and ranking snapshot."""

    effective_now = now or datetime.now(timezone.utc)
    state = _ensure_user_state(db)
    latest_annotation_expiry = _latest_annotation_expiry(db)
    recent_exposure_counts = _recent_unaccepted_exposure_counts(db, effective_now)
    active_nodes = db.scalars(
        select(ActionNode).where(
            ActionNode.user_id == settings.default_user_id,
            ActionNode.status == "active",
        )
    ).all()

    scored_candidates = []
    for node in active_nodes:
        candidate = _score_node(
            node,
            state,
            latest_annotation_expiry.get(node.node_id),
            recent_exposure_counts,
            active_nodes,
            effective_now,
        )
        if candidate is not None:
            scored_candidates.append(candidate)

    scored_candidates.sort(key=lambda candidate: (candidate.score, candidate.node.updated_at), reverse=True)
    ranking_snapshot = {
        str(candidate.node.node_id): {
            "score": candidate.score,
            "reason_tags": candidate.reason_tags,
            "breakdown": candidate.breakdown,
        }
        for candidate in scored_candidates
    }
    return state, scored_candidates, ranking_snapshot
