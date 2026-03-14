"""Dry-run replay and rebuild helpers for the authoritative state loop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot
from app.services.state_service import _snapshot_from_model

settings = get_settings()

CANONICAL_SHADOW_RESULTS = ("exact_match", "compatible_match", "drift", "shadow_failed")


def clamp_energy(value: int) -> int:
    """Clamp an energy value to the canonical user-state range."""

    return max(0, min(100, value))


def build_genesis_state_snapshot() -> UserStateSnapshot:
    """Return the default dry-run genesis state without mutating storage."""

    return UserStateSnapshot(
        mental_energy=100,
        physical_energy=100,
        focus_mode="unknown",
        do_not_disturb_until=None,
        recent_context=None,
        last_updated_at=None,
    )


def snapshot_from_state_dict(state_data: dict[str, Any] | None) -> UserStateSnapshot:
    """Normalize a persisted JSON snapshot into the shared state schema."""

    payload = dict(state_data or {})
    payload.setdefault("mental_energy", 100)
    payload.setdefault("physical_energy", 100)
    payload.setdefault("focus_mode", "unknown")
    payload.setdefault("do_not_disturb_until", None)
    payload.setdefault("recent_context", None)
    payload.setdefault("last_updated_at", None)
    return UserStateSnapshot.model_validate(payload)


def snapshot_to_dict(snapshot: UserStateSnapshot) -> dict[str, Any]:
    """Serialize a snapshot to a stable JSON-safe dict."""

    payload = snapshot.model_dump(mode="python")
    for field in ("do_not_disturb_until", "last_updated_at"):
        value = payload.get(field)
        if isinstance(value, datetime):
            payload[field] = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return payload


def diff_snapshots(expected: UserStateSnapshot, actual: UserStateSnapshot) -> dict[str, dict[str, Any]]:
    """Return a stable top-level diff between two state snapshots."""

    expected_payload = snapshot_to_dict(expected)
    actual_payload = snapshot_to_dict(actual)
    return {
        field: {"expected": expected_payload[field], "actual": actual_payload[field]}
        for field in expected_payload
        if expected_payload[field] != actual_payload.get(field)
    }


def reduce_state_snapshot(
    current_state: UserStateSnapshot,
    impact: dict[str, Any],
    *,
    updated_at: datetime | None,
) -> UserStateSnapshot:
    """Apply one authoritative parsed impact to a snapshot without writing storage."""

    return UserStateSnapshot(
        mental_energy=clamp_energy(current_state.mental_energy + int(impact.get("mental_delta", 0))),
        physical_energy=clamp_energy(current_state.physical_energy + int(impact.get("physical_delta", 0))),
        focus_mode=impact.get("focus_mode") or current_state.focus_mode,
        do_not_disturb_until=current_state.do_not_disturb_until,
        recent_context=impact.get("event_summary"),
        last_updated_at=updated_at,
    )


def get_persisted_or_genesis_state(db: Session, user_id: str) -> UserStateSnapshot:
    """Load the persisted snapshot if present, otherwise return genesis without writes."""

    state = db.get(UserState, user_id)
    if state is None:
        return build_genesis_state_snapshot()
    return _snapshot_from_model(state)


def _ordered_event_patch_query(
    user_id: str,
    *,
    after_cursor: tuple[datetime, int] | None,
    to_created_at: datetime | None,
) -> Select[tuple[StateHistory]]:
    query = (
        select(StateHistory)
        .where(
            StateHistory.user_id == user_id,
            StateHistory.change_reason == "event_patch",
            StateHistory.event_id.is_not(None),
        )
        .order_by(StateHistory.created_at.asc(), StateHistory.id.asc())
    )
    if after_cursor is not None:
        after_created_at, after_id = after_cursor
        query = query.where(
            or_(
                StateHistory.created_at > after_created_at,
                and_(
                    StateHistory.created_at == after_created_at,
                    StateHistory.id > after_id,
                ),
            )
        )
    if to_created_at is not None:
        query = query.where(StateHistory.created_at <= to_created_at)
    return query


def _select_anchor_state_history(
    db: Session,
    *,
    user_id: str,
    from_state_history_id: int | None,
    from_created_at: datetime | None,
    to_created_at: datetime | None,
) -> StateHistory | None:
    if from_state_history_id is not None:
        anchor = db.get(StateHistory, from_state_history_id)
        if anchor is None or anchor.user_id != user_id:
            raise ValueError(f"state_history {from_state_history_id} not found for user {user_id}")
        return anchor

    query = (
        select(StateHistory)
        .where(
            StateHistory.user_id == user_id,
            StateHistory.change_reason != "event_patch",
        )
        .order_by(StateHistory.created_at.desc(), StateHistory.id.desc())
    )
    if from_created_at is not None:
        query = query.where(StateHistory.created_at <= from_created_at)
    elif to_created_at is not None:
        query = query.where(StateHistory.created_at <= to_created_at)
    return db.scalar(query.limit(1))


def build_event_replay_report(db: Session, event_id: UUID | str) -> dict[str, Any]:
    """Build a dry-run report for one persisted event."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    history = db.scalar(
        select(StateHistory)
        .where(
            StateHistory.event_id == event.event_id,
            StateHistory.change_reason == "event_patch",
        )
        .order_by(StateHistory.created_at.desc(), StateHistory.id.desc())
        .limit(1)
    )

    report: dict[str, Any] = {
        "event": {
            "event_id": str(event.event_id),
            "user_id": event.user_id,
            "source": event.source,
            "source_event_type": event.source_event_type,
            "parse_status": event.parse_status,
            "occurred_at": event.occurred_at.isoformat(),
            "created_at": event.created_at.isoformat(),
        },
        "authoritative_parsed_impact": dict(event.parsed_impact or {}),
        "parse_metadata": dict(event.parse_metadata or {}),
        "recorded_before_state": None,
        "recorded_after_state": None,
        "recomputed_after_state": None,
        "top_level_diff": {},
        "replay_result": "not_applied",
    }

    if history is None:
        return report

    recorded_before = snapshot_from_state_dict(history.before_state)
    recorded_after = snapshot_from_state_dict(history.after_state)
    report["recorded_before_state"] = snapshot_to_dict(recorded_before)
    report["recorded_after_state"] = snapshot_to_dict(recorded_after)
    report["state_history"] = {
        "state_history_id": history.id,
        "change_reason": history.change_reason,
        "created_at": history.created_at.isoformat(),
    }

    if event.parse_status == "failed" or not event.parsed_impact:
        report["replay_result"] = "drift"
        report["top_level_diff"] = {"parsed_impact": {"expected": report["recorded_after_state"], "actual": None}}
        return report

    recomputed_after = reduce_state_snapshot(
        recorded_before,
        dict(event.parsed_impact or {}),
        updated_at=recorded_after.last_updated_at,
    )
    report["recomputed_after_state"] = snapshot_to_dict(recomputed_after)
    report["top_level_diff"] = diff_snapshots(recorded_after, recomputed_after)
    report["replay_result"] = "exact_match" if not report["top_level_diff"] else "drift"
    return report


def build_rebuild_state_report(
    db: Session,
    *,
    user_id: str | None = None,
    from_state_history_id: int | None = None,
    from_created_at: datetime | None = None,
    to_created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a dry-run rebuild report from a checkpoint over authoritative history."""

    target_user_id = user_id or settings.default_user_id
    anchor_history = _select_anchor_state_history(
        db,
        user_id=target_user_id,
        from_state_history_id=from_state_history_id,
        from_created_at=from_created_at,
        to_created_at=to_created_at,
    )

    if anchor_history is not None:
        anchor_snapshot = snapshot_from_state_dict(anchor_history.after_state)
        anchor_cursor = (anchor_history.created_at, anchor_history.id)
        anchor = {
            "source": "state_history",
            "state_history_id": anchor_history.id,
            "change_reason": anchor_history.change_reason,
            "created_at": anchor_history.created_at.isoformat(),
            "snapshot": snapshot_to_dict(anchor_snapshot),
        }
    else:
        anchor_snapshot = build_genesis_state_snapshot()
        anchor_cursor = None
        anchor = {
            "source": "genesis",
            "state_history_id": None,
            "change_reason": "genesis_default",
            "created_at": None,
            "snapshot": snapshot_to_dict(anchor_snapshot),
        }

    replay_rows = db.scalars(
        _ordered_event_patch_query(
            target_user_id,
            after_cursor=anchor_cursor,
            to_created_at=to_created_at,
        )
    ).all()
    event_ids = [row.event_id for row in replay_rows if row.event_id is not None]
    event_map = {
        event.event_id: event
        for event in db.scalars(select(EventLog).where(EventLog.event_id.in_(event_ids))).all()
    } if event_ids else {}

    rebuilt_snapshot = anchor_snapshot
    drift_events: list[dict[str, Any]] = []
    shadow_summary = {key: 0 for key in CANONICAL_SHADOW_RESULTS}

    for row in replay_rows:
        event = event_map.get(row.event_id)
        recorded_before = snapshot_from_state_dict(row.before_state)
        recorded_after = snapshot_from_state_dict(row.after_state)
        before_diff = diff_snapshots(recorded_before, rebuilt_snapshot)

        if event is None or event.parse_status == "failed" or not event.parsed_impact:
            drift_events.append(
                {
                    "state_history_id": row.id,
                    "event_id": str(row.event_id) if row.event_id is not None else None,
                    "result": "not_applied",
                    "reason": "missing_event_or_failed_parse",
                    "before_diff": before_diff,
                }
            )
            continue

        comparison_result = (event.parse_metadata or {}).get("comparison_result")
        if comparison_result in shadow_summary:
            shadow_summary[comparison_result] += 1

        recomputed_after = reduce_state_snapshot(
            rebuilt_snapshot,
            dict(event.parsed_impact or {}),
            updated_at=recorded_after.last_updated_at,
        )
        after_diff = diff_snapshots(recorded_after, recomputed_after)
        if before_diff or after_diff:
            drift_events.append(
                {
                    "state_history_id": row.id,
                    "event_id": str(event.event_id),
                    "result": "drift",
                    "event_type": event.parsed_impact.get("event_type"),
                    "before_diff": before_diff,
                    "after_diff": after_diff,
                }
            )

        rebuilt_snapshot = recomputed_after

    current_state = get_persisted_or_genesis_state(db, target_user_id)
    if to_created_at is None:
        comparison_target = {
            "source": "current_user_state",
            "state_history_id": None,
            "created_at": snapshot_to_dict(current_state)["last_updated_at"],
            "snapshot": snapshot_to_dict(current_state),
        }
        comparison_snapshot = current_state
    elif replay_rows:
        last_replayed_row = replay_rows[-1]
        comparison_snapshot = snapshot_from_state_dict(last_replayed_row.after_state)
        comparison_target = {
            "source": "last_replayed_state_history",
            "state_history_id": last_replayed_row.id,
            "created_at": last_replayed_row.created_at.isoformat(),
            "snapshot": snapshot_to_dict(comparison_snapshot),
        }
    else:
        comparison_snapshot = anchor_snapshot
        comparison_target = {
            "source": "anchor_snapshot",
            "state_history_id": anchor.get("state_history_id"),
            "created_at": anchor.get("created_at"),
            "snapshot": snapshot_to_dict(comparison_snapshot),
        }
    top_level_diff = diff_snapshots(comparison_snapshot, rebuilt_snapshot)

    upper_bound = to_created_at or datetime.now(timezone.utc)
    event_query = select(EventLog).where(EventLog.user_id == target_user_id)
    if anchor_cursor is not None:
        event_query = event_query.where(EventLog.created_at >= anchor_cursor[0])
    elif from_created_at is not None:
        event_query = event_query.where(EventLog.created_at >= from_created_at)
    event_query = event_query.where(EventLog.created_at <= upper_bound)
    events_in_range = db.scalars(event_query).all()
    replayed_event_ids = {row.event_id for row in replay_rows if row.event_id is not None}
    parse_failed_count = sum(1 for event in events_in_range if event.parse_status == "failed")
    unapplied_event_count = sum(
        1
        for event in events_in_range
        if event.parse_status != "failed" and event.event_id not in replayed_event_ids
    )

    if anchor["source"] == "genesis":
        summary_status = "checkpoint_gap"
    elif top_level_diff or drift_events:
        summary_status = "drift_detected"
    else:
        summary_status = "clean"

    return {
        "user_id": target_user_id,
        "summary_status": summary_status,
        "anchor": anchor,
        "comparison_target": comparison_target,
        "replayed_event_count": len(replay_rows),
        "rebuilt_state": snapshot_to_dict(rebuilt_snapshot),
        "current_persisted_state": snapshot_to_dict(current_state),
        "top_level_diff": top_level_diff,
        "drift_events": drift_events,
        "event_stats": {
            "parse_failed_count": parse_failed_count,
            "unapplied_event_count": unapplied_event_count,
        },
        "shadow_comparison_summary": shadow_summary,
        "range": {
            "from_state_history_id": from_state_history_id,
            "from_created_at": from_created_at.isoformat() if from_created_at is not None else None,
            "to_created_at": to_created_at.isoformat() if to_created_at is not None else None,
        },
    }
