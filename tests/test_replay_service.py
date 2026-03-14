from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot
from app.services.event_processing import apply_state_patch_from_event, parse_event_log
from app.services.replay_service import (
    build_event_replay_report,
    build_rebuild_state_report,
    diff_snapshots,
    reduce_state_snapshot,
    snapshot_from_state_dict,
    snapshot_to_dict,
)

settings = get_settings()


def _persist_event_log(session, *, event_id, raw_text: str | None, external_prefix: str) -> None:
    session.add(
        EventLog(
            event_id=event_id,
            user_id=settings.default_user_id,
            source="desktop_plugin",
            source_event_type="text",
            external_event_id=f"{external_prefix}-{event_id}",
            payload_hash=f"{external_prefix}-{event_id}",
            raw_text=raw_text,
            raw_payload={"text": raw_text} if raw_text is not None else None,
            occurred_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _snapshot(
    *,
    mental: int,
    physical: int,
    focus: str,
    recent_context: str | None,
    updated_at: datetime | None,
) -> dict:
    return UserStateSnapshot(
        mental_energy=mental,
        physical_energy=physical,
        focus_mode=focus,
        do_not_disturb_until=None,
        recent_context=recent_context,
        last_updated_at=updated_at,
    ).model_dump(mode="json")


def _persist_custom_user_state(session, *, user_id: str, snapshot: dict, state_version: int = 1) -> None:
    session.add(
        UserState(
            user_id=user_id,
            state_version=state_version,
            mental_energy=snapshot["mental_energy"],
            physical_energy=snapshot["physical_energy"],
            focus_mode=snapshot["focus_mode"],
            do_not_disturb_until=snapshot["do_not_disturb_until"],
            recent_context=snapshot["recent_context"],
            updated_at=snapshot["last_updated_at"],
        )
    )
    session.commit()


def _persist_custom_event(
    session,
    *,
    event_id,
    user_id: str,
    text: str,
    parsed_impact: dict,
    parse_status: str,
    occurred_at: datetime,
    created_at: datetime,
    comparison_result: str | None = None,
) -> None:
    parse_metadata = {"primary": {"provider": "deterministic"}}
    if comparison_result is not None:
        parse_metadata["comparison_result"] = comparison_result
    session.add(
        EventLog(
            event_id=event_id,
            user_id=user_id,
            source="frontend_web_shell",
            source_event_type="text",
            external_event_id=f"{user_id}-{event_id}",
            payload_hash=f"{user_id}-{event_id}",
            raw_text=text,
            raw_payload={"text": text},
            parsed_impact=parsed_impact,
            parse_metadata=parse_metadata,
            parse_status=parse_status,
            occurred_at=occurred_at,
            ingested_at=created_at,
            created_at=created_at,
        )
    )
    session.commit()


def _persist_state_history(
    session,
    *,
    user_id: str,
    event_id,
    before_state: dict,
    after_state: dict,
    change_reason: str,
    created_at: datetime,
) -> None:
    session.add(
        StateHistory(
            user_id=user_id,
            event_id=event_id,
            before_state=before_state,
            after_state=after_state,
            change_reason=change_reason,
            created_at=created_at,
        )
    )
    session.commit()


def _cleanup_custom_user(session, user_id: str) -> None:
    event_ids = session.scalars(select(EventLog.event_id).where(EventLog.user_id == user_id)).all()
    if event_ids:
        session.execute(delete(StateHistory).where(StateHistory.event_id.in_(event_ids)))
        session.execute(delete(EventLog).where(EventLog.event_id.in_(event_ids)))
    session.execute(delete(StateHistory).where(StateHistory.user_id == user_id))
    session.execute(delete(UserState).where(UserState.user_id == user_id))
    session.commit()


def test_state_reducer_matches_recorded_history_for_success_patch(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="replay-success",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))
            event = session.get(EventLog, event_id)

            recorded_before = snapshot_from_state_dict(history.before_state)
            recorded_after = snapshot_from_state_dict(history.after_state)
            recomputed_after = reduce_state_snapshot(
                recorded_before,
                event.parsed_impact,
                updated_at=recorded_after.last_updated_at,
            )

            assert diff_snapshots(recorded_after, recomputed_after) == {}
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_state_reducer_matches_recorded_history_for_fallback_patch(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="今天随便记一下当前想法。",
            external_prefix="replay-fallback",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))
            event = session.get(EventLog, event_id)

            recorded_before = snapshot_from_state_dict(history.before_state)
            recorded_after = snapshot_from_state_dict(history.after_state)
            recomputed_after = reduce_state_snapshot(
                recorded_before,
                event.parsed_impact,
                updated_at=recorded_after.last_updated_at,
            )

            assert diff_snapshots(recorded_after, recomputed_after) == {}
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_build_event_replay_report_exact_match(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="replay-report-exact",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)

            report = build_event_replay_report(session, event_id)

            assert report["replay_result"] == "exact_match"
            assert report["parse_metadata"]["primary"]["provider"] == "deterministic"
            assert report["top_level_diff"] == {}
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_build_event_replay_report_detects_drift(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="replay-report-drift",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))
            altered_after = dict(history.after_state)
            altered_after["mental_energy"] += 1
            history.after_state = altered_after
            session.add(history)
            session.commit()

            report = build_event_replay_report(session, event_id)

            assert report["replay_result"] == "drift"
            assert "mental_energy" in report["top_level_diff"]
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_build_event_replay_report_marks_not_applied(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="replay-report-not-applied",
        )

        try:
            parse_event_log(session, event_id)
            report = build_event_replay_report(session, event_id)

            assert report["replay_result"] == "not_applied"
            assert report["recorded_after_state"] is None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_build_event_replay_report_uses_latest_event_patch_state_history():
    user_id = f"replay-latest-{uuid4()}"
    event_id = uuid4()
    event_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=event_at - timedelta(minutes=1),
    )
    after_one = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_at,
    )
    after_two = _snapshot(
        mental=60,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_at + timedelta(seconds=1),
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_two, state_version=3)
            _persist_custom_event(
                session,
                event_id=event_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_at,
                created_at=event_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_id,
                before_state=checkpoint_state,
                after_state=after_one,
                change_reason="event_patch",
                created_at=event_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_id,
                before_state=after_one,
                after_state=after_two,
                change_reason="event_patch",
                created_at=event_at + timedelta(seconds=1),
            )

            report = build_event_replay_report(session, event_id)

            assert report["replay_result"] == "exact_match"
            assert datetime.fromisoformat(report["state_history"]["created_at"]).astimezone(timezone.utc) == (
                event_at + timedelta(seconds=1)
            )
            assert report["recorded_before_state"]["mental_energy"] == 80
            assert report["recorded_after_state"]["mental_energy"] == 60
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_uses_latest_checkpoint_and_reports_clean():
    user_id = f"rebuild-clean-{uuid4()}"
    event_one_id = uuid4()
    event_two_id = uuid4()
    checkpoint_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    event_one_at = checkpoint_at + timedelta(minutes=1)
    event_two_at = checkpoint_at + timedelta(minutes=2)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=checkpoint_at,
    )
    genesis_state = _snapshot(
        mental=100,
        physical=100,
        focus="unknown",
        recent_context=None,
        updated_at=None,
    )
    after_one = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_one_at,
    )
    after_two = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="今天随便记一下当前想法。",
        updated_at=event_two_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_two, state_version=3)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=genesis_state,
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=checkpoint_at,
            )
            _persist_custom_event(
                session,
                event_id=event_one_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_one_at,
                created_at=event_one_at,
                comparison_result="exact_match",
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_one_id,
                before_state=checkpoint_state,
                after_state=after_one,
                change_reason="event_patch",
                created_at=event_one_at,
            )
            _persist_custom_event(
                session,
                event_id=event_two_id,
                user_id=user_id,
                text="今天随便记一下当前想法。",
                parsed_impact={
                    "event_summary": "今天随便记一下当前想法。",
                    "event_type": "other",
                    "mental_delta": 0,
                    "physical_delta": 0,
                    "focus_mode": "",
                    "tags": [],
                    "should_offer_pull_hint": False,
                    "confidence": 0.3,
                },
                parse_status="fallback",
                occurred_at=event_two_at,
                created_at=event_two_at,
                comparison_result="compatible_match",
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_two_id,
                before_state=after_one,
                after_state=after_two,
                change_reason="event_patch",
                created_at=event_two_at,
            )

            report = build_rebuild_state_report(session, user_id=user_id)

            assert report["summary_status"] == "clean"
            assert report["anchor"]["source"] == "state_history"
            assert report["replayed_event_count"] == 2
            assert report["top_level_diff"] == {}
            assert report["shadow_comparison_summary"]["exact_match"] == 1
            assert report["shadow_comparison_summary"]["compatible_match"] == 1
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_bounded_window_compares_to_last_replayed_state_history():
    user_id = f"rebuild-bounded-{uuid4()}"
    event_one_id = uuid4()
    event_two_id = uuid4()
    event_three_id = uuid4()
    checkpoint_at = datetime.now(timezone.utc) - timedelta(minutes=4)
    event_one_at = checkpoint_at + timedelta(minutes=1)
    event_two_at = checkpoint_at + timedelta(minutes=2)
    event_three_at = checkpoint_at + timedelta(minutes=3)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=checkpoint_at,
    )
    after_one = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_one_at,
    )
    after_two = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="今天随便记一下当前想法。",
        updated_at=event_two_at,
    )
    after_three = _snapshot(
        mental=95,
        physical=100,
        focus="recovered",
        recent_context="I took a real break and recovered.",
        updated_at=event_three_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_three, state_version=4)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=_snapshot(
                    mental=100,
                    physical=100,
                    focus="unknown",
                    recent_context=None,
                    updated_at=None,
                ),
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=checkpoint_at,
            )
            _persist_custom_event(
                session,
                event_id=event_one_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_one_at,
                created_at=event_one_at,
                comparison_result="exact_match",
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_one_id,
                before_state=checkpoint_state,
                after_state=after_one,
                change_reason="event_patch",
                created_at=event_one_at,
            )
            _persist_custom_event(
                session,
                event_id=event_two_id,
                user_id=user_id,
                text="今天随便记一下当前想法。",
                parsed_impact={
                    "event_summary": "今天随便记一下当前想法。",
                    "event_type": "other",
                    "mental_delta": 0,
                    "physical_delta": 0,
                    "focus_mode": "",
                    "tags": [],
                    "should_offer_pull_hint": False,
                    "confidence": 0.3,
                },
                parse_status="fallback",
                occurred_at=event_two_at,
                created_at=event_two_at,
                comparison_result="compatible_match",
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_two_id,
                before_state=after_one,
                after_state=after_two,
                change_reason="event_patch",
                created_at=event_two_at,
            )
            _persist_custom_event(
                session,
                event_id=event_three_id,
                user_id=user_id,
                text="I took a real break and recovered.",
                parsed_impact={
                    "event_summary": "I took a real break and recovered.",
                    "event_type": "rest",
                    "mental_delta": 15,
                    "physical_delta": 0,
                    "focus_mode": "recovered",
                    "tags": ["recovery"],
                    "should_offer_pull_hint": False,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_three_at,
                created_at=event_three_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_three_id,
                before_state=after_two,
                after_state=after_three,
                change_reason="event_patch",
                created_at=event_three_at,
            )

            report = build_rebuild_state_report(session, user_id=user_id, to_created_at=event_two_at)

            assert report["summary_status"] == "clean"
            assert report["comparison_target"]["source"] == "last_replayed_state_history"
            assert report["comparison_target"]["snapshot"]["mental_energy"] == 80
            assert report["current_persisted_state"]["mental_energy"] == 95
            assert report["top_level_diff"] == {}
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_includes_event_patch_at_same_timestamp_as_anchor():
    user_id = f"rebuild-same-ts-{uuid4()}"
    event_id = uuid4()
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=1)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=timestamp,
    )
    after_event = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=timestamp,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_event, state_version=2)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=_snapshot(
                    mental=100,
                    physical=100,
                    focus="unknown",
                    recent_context=None,
                    updated_at=None,
                ),
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=timestamp,
            )
            _persist_custom_event(
                session,
                event_id=event_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=timestamp,
                created_at=timestamp,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_id,
                before_state=checkpoint_state,
                after_state=after_event,
                change_reason="event_patch",
                created_at=timestamp,
            )

            report = build_rebuild_state_report(session, user_id=user_id)

            assert report["summary_status"] == "clean"
            assert report["replayed_event_count"] == 1
            assert report["top_level_diff"] == {}
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_uses_anchor_snapshot_when_bounded_window_has_no_rows():
    user_id = f"rebuild-anchor-only-{uuid4()}"
    event_id = uuid4()
    checkpoint_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    later_event_at = checkpoint_at + timedelta(minutes=1)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=checkpoint_at,
    )
    after_later_event = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=later_event_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_later_event, state_version=2)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=_snapshot(
                    mental=100,
                    physical=100,
                    focus="unknown",
                    recent_context=None,
                    updated_at=None,
                ),
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=checkpoint_at,
            )
            _persist_custom_event(
                session,
                event_id=event_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=later_event_at,
                created_at=later_event_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_id,
                before_state=checkpoint_state,
                after_state=after_later_event,
                change_reason="event_patch",
                created_at=later_event_at,
            )

            report = build_rebuild_state_report(
                session,
                user_id=user_id,
                to_created_at=checkpoint_at + timedelta(seconds=30),
            )

            assert report["summary_status"] == "clean"
            assert report["comparison_target"]["source"] == "anchor_snapshot"
            assert report["replayed_event_count"] == 0
            assert report["top_level_diff"] == {}
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_bounds_event_stats_to_requested_window():
    user_id = f"rebuild-stats-{uuid4()}"
    event_one_id = uuid4()
    failed_event_id = uuid4()
    checkpoint_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    event_one_at = checkpoint_at + timedelta(minutes=1)
    failed_event_at = checkpoint_at + timedelta(minutes=2)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=checkpoint_at,
    )
    after_one = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_one_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_one, state_version=2)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=_snapshot(
                    mental=100,
                    physical=100,
                    focus="unknown",
                    recent_context=None,
                    updated_at=None,
                ),
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=checkpoint_at,
            )
            _persist_custom_event(
                session,
                event_id=event_one_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_one_at,
                created_at=event_one_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_one_id,
                before_state=checkpoint_state,
                after_state=after_one,
                change_reason="event_patch",
                created_at=event_one_at,
            )
            _persist_custom_event(
                session,
                event_id=failed_event_id,
                user_id=user_id,
                text="broken parse event",
                parsed_impact={},
                parse_status="failed",
                occurred_at=failed_event_at,
                created_at=failed_event_at,
            )

            report = build_rebuild_state_report(session, user_id=user_id, to_created_at=event_one_at)

            assert report["summary_status"] == "clean"
            assert report["event_stats"]["parse_failed_count"] == 0
            assert report["event_stats"]["unapplied_event_count"] == 0
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_counts_failed_events_at_anchor_timestamp():
    user_id = f"rebuild-stats-anchor-ts-{uuid4()}"
    failed_event_id = uuid4()
    checkpoint_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    checkpoint_state = _snapshot(
        mental=100,
        physical=100,
        focus="recovered",
        recent_context="manual reset",
        updated_at=checkpoint_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=checkpoint_state, state_version=1)
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=None,
                before_state=_snapshot(
                    mental=100,
                    physical=100,
                    focus="unknown",
                    recent_context=None,
                    updated_at=None,
                ),
                after_state=checkpoint_state,
                change_reason="manual reset",
                created_at=checkpoint_at,
            )
            _persist_custom_event(
                session,
                event_id=failed_event_id,
                user_id=user_id,
                text="failed parse at anchor timestamp",
                parsed_impact={},
                parse_status="failed",
                occurred_at=checkpoint_at,
                created_at=checkpoint_at,
            )

            report = build_rebuild_state_report(session, user_id=user_id, to_created_at=checkpoint_at)

            assert report["summary_status"] == "clean"
            assert report["replayed_event_count"] == 0
            assert report["event_stats"]["parse_failed_count"] == 1
        finally:
            _cleanup_custom_user(session, user_id)


def test_build_rebuild_state_report_uses_genesis_when_no_checkpoint_exists():
    user_id = f"rebuild-genesis-{uuid4()}"
    event_id = uuid4()
    event_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    genesis_state = _snapshot(
        mental=100,
        physical=100,
        focus="unknown",
        recent_context=None,
        updated_at=None,
    )
    after_event = _snapshot(
        mental=80,
        physical=100,
        focus="tired",
        recent_context="I am drained after debugging all afternoon.",
        updated_at=event_at,
    )

    with SessionLocal() as session:
        try:
            _persist_custom_user_state(session, user_id=user_id, snapshot=after_event, state_version=2)
            _persist_custom_event(
                session,
                event_id=event_id,
                user_id=user_id,
                text="I am drained after debugging all afternoon.",
                parsed_impact={
                    "event_summary": "I am drained after debugging all afternoon.",
                    "event_type": "chat_update",
                    "mental_delta": -20,
                    "physical_delta": 0,
                    "focus_mode": "tired",
                    "tags": ["mental_load"],
                    "should_offer_pull_hint": True,
                    "confidence": 0.7,
                },
                parse_status="success",
                occurred_at=event_at,
                created_at=event_at,
            )
            _persist_state_history(
                session,
                user_id=user_id,
                event_id=event_id,
                before_state=genesis_state,
                after_state=after_event,
                change_reason="event_patch",
                created_at=event_at,
            )

            report = build_rebuild_state_report(session, user_id=user_id)

            assert report["summary_status"] == "checkpoint_gap"
            assert report["anchor"]["source"] == "genesis"
            assert report["replayed_event_count"] == 1
        finally:
            _cleanup_custom_user(session, user_id)
