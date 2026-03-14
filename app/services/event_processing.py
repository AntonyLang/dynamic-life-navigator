"""Deterministic event parsing and state patch application."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot
from app.schemas.parsing import ParserDecisionDTO, ParserImpactDTO
from app.services.parser_provider import get_event_parser_provider, get_shadow_event_parser_provider
from app.services.state_service import _ensure_user_state, _snapshot_from_model

logger = logging.getLogger(__name__)


def _clamp_energy(value: int) -> int:
    return max(0, min(100, value))


def _decision_metadata_dict(decision: ParserDecisionDTO) -> dict[str, Any]:
    return decision.metadata.model_dump(mode="json")


def _impact_dict(impact: ParserImpactDTO | None) -> dict[str, Any]:
    return impact.model_dump(mode="json") if impact is not None else {}


def _get_parse_metadata(event: EventLog) -> dict[str, Any]:
    return dict(event.parse_metadata or {})


def _set_primary_parse_metadata(event: EventLog, decision: ParserDecisionDTO) -> None:
    parse_metadata = _get_parse_metadata(event)
    parse_metadata["primary"] = _decision_metadata_dict(decision)
    event.parse_metadata = parse_metadata


def _normalize_tags(impact: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(tag) for tag in impact.get("tags", []) if isinstance(tag, str)))


def _is_exact_match(primary_impact: dict[str, Any], shadow_impact: dict[str, Any]) -> bool:
    return (
        primary_impact.get("event_type") == shadow_impact.get("event_type")
        and primary_impact.get("focus_mode", "") == shadow_impact.get("focus_mode", "")
        and int(primary_impact.get("mental_delta", 0)) == int(shadow_impact.get("mental_delta", 0))
        and int(primary_impact.get("physical_delta", 0)) == int(shadow_impact.get("physical_delta", 0))
        and bool(primary_impact.get("should_offer_pull_hint")) == bool(shadow_impact.get("should_offer_pull_hint"))
        and _normalize_tags(primary_impact) == _normalize_tags(shadow_impact)
    )


def _is_compatible_match(primary_impact: dict[str, Any], shadow_impact: dict[str, Any]) -> bool:
    return (
        primary_impact.get("event_type") == shadow_impact.get("event_type")
        and primary_impact.get("focus_mode", "") == shadow_impact.get("focus_mode", "")
        and abs(int(primary_impact.get("mental_delta", 0)) - int(shadow_impact.get("mental_delta", 0))) <= 5
        and abs(int(primary_impact.get("physical_delta", 0)) - int(shadow_impact.get("physical_delta", 0))) <= 5
    )


def _classify_shadow_comparison(primary_impact: dict[str, Any], shadow_decision: ParserDecisionDTO) -> str:
    if shadow_decision.metadata.fallback_reason is not None or shadow_decision.status == "failed" or shadow_decision.impact is None:
        return "shadow_failed"

    shadow_impact = _impact_dict(shadow_decision.impact)
    if _is_exact_match(primary_impact, shadow_impact):
        return "exact_match"
    if _is_compatible_match(primary_impact, shadow_impact):
        return "compatible_match"
    return "drift"


def compare_shadow_parser_decision(db: Session, event_id: UUID | str) -> dict[str, Any]:
    """Run a non-authoritative shadow parse and record comparison metadata."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    shadow_provider = get_shadow_event_parser_provider()
    if shadow_provider is None:
        return {"status": "skipped", "event_id": str(event_id), "reason": "shadow_disabled_or_same_provider"}

    if not event.parsed_impact:
        return {"status": "skipped", "event_id": str(event_id), "reason": "primary_parse_missing"}

    shadow_decision = shadow_provider.parse(event)
    comparison_result = _classify_shadow_comparison(event.parsed_impact, shadow_decision)

    parse_metadata = _get_parse_metadata(event)
    parse_metadata["shadow"] = {
        "shadow_provider": shadow_decision.metadata.provider,
        "shadow_parser_version": shadow_decision.metadata.parser_version,
        "shadow_prompt_version": shadow_decision.metadata.prompt_version,
        "shadow_model_name": shadow_decision.metadata.model_name,
        "shadow_status": shadow_decision.status,
        "shadow_fallback_reason": shadow_decision.metadata.fallback_reason,
        "shadow_error_detail": shadow_decision.metadata.error_detail,
    }
    parse_metadata["comparison_result"] = comparison_result
    event.parse_metadata = parse_metadata
    db.add(event)
    db.commit()
    db.refresh(event)

    log_event(
        logger,
        logging.INFO,
        "shadow parser compared",
        event_id=event.event_id,
        user_id=event.user_id,
        parser_provider=parse_metadata.get("primary", {}).get("provider"),
        shadow_provider=shadow_decision.metadata.provider,
        comparison_result=comparison_result,
        shadow_fallback_reason=shadow_decision.metadata.fallback_reason,
        shadow_error_detail=shadow_decision.metadata.error_detail,
    )
    return {
        "status": "compared",
        "event_id": str(event.event_id),
        "comparison_result": comparison_result,
    }


def parse_event_log(db: Session, event_id: UUID | str) -> dict[str, Any]:
    """Parse a persisted event into a minimal structured impact."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    provider = get_event_parser_provider()
    decision = provider.parse(event)
    event.parsed_impact = _impact_dict(decision.impact)
    event.parse_status = decision.status
    _set_primary_parse_metadata(event, decision)
    db.add(event)
    db.commit()
    db.refresh(event)
    log_event(
        logger,
        logging.INFO,
        "event parsed",
        event_id=event.event_id,
        user_id=event.user_id,
        parse_status=event.parse_status,
        event_type=event.parsed_impact.get("event_type") if event.parsed_impact else None,
        parser_provider=decision.metadata.provider,
        parser_version=decision.metadata.parser_version,
        prompt_version=decision.metadata.prompt_version,
        model_name=decision.metadata.model_name,
        fallback_reason=decision.metadata.fallback_reason,
        provider_error=decision.metadata.error_detail,
    )
    return event.parsed_impact


def apply_state_patch_from_event(
    db: Session,
    event_id: UUID | str,
    *,
    max_retries: int = 2,
) -> UserStateSnapshot:
    """Apply a deterministic state patch using optimistic concurrency."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    if not event.parsed_impact:
        parse_event_log(db, event_id)
        db.refresh(event)

    state = _ensure_user_state(db)
    if event.parse_status == "failed" or not event.parsed_impact:
        log_event(
            logger,
            logging.INFO,
            "state patch skipped after parse failure",
            event_id=event.event_id,
            user_id=state.user_id,
            parse_status=event.parse_status,
            state_version=state.state_version,
        )
        return _snapshot_from_model(state)

    impact = event.parsed_impact
    for _ in range(max_retries):
        state = db.get(UserState, state.user_id)
        expected_version = state.state_version
        before_snapshot = _snapshot_from_model(state).model_dump(mode="json")

        new_mental = _clamp_energy(state.mental_energy + int(impact.get("mental_delta", 0)))
        new_physical = _clamp_energy(state.physical_energy + int(impact.get("physical_delta", 0)))
        new_focus = impact.get("focus_mode") or state.focus_mode
        now = datetime.now(timezone.utc)

        result = db.execute(
            update(UserState)
            .where(
                UserState.user_id == state.user_id,
                UserState.state_version == expected_version,
            )
            .values(
                state_version=expected_version + 1,
                mental_energy=new_mental,
                physical_energy=new_physical,
                focus_mode=new_focus,
                recent_context=impact.get("event_summary"),
                source_last_event_id=event.event_id,
                source_last_event_at=event.occurred_at,
                updated_at=now,
            )
        )
        if result.rowcount == 1:
            updated_state = db.scalar(select(UserState).where(UserState.user_id == state.user_id))
            db.add(
                StateHistory(
                    user_id=updated_state.user_id,
                    event_id=event.event_id,
                    before_state=before_snapshot,
                    after_state=_snapshot_from_model(updated_state).model_dump(mode="json"),
                    change_reason="event_patch",
                )
            )
            db.commit()
            log_event(
                logger,
                logging.INFO,
                "state patch applied",
                event_id=event.event_id,
                user_id=updated_state.user_id,
                parse_status=event.parse_status,
                state_version=updated_state.state_version,
            )
            return _snapshot_from_model(updated_state)

        db.rollback()

    raise RuntimeError(f"failed to apply state patch for event {event_id} after {max_retries} retries")
