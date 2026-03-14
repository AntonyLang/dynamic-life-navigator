from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.action_node import ActionNode
from app.models.event_log import EventLog
from app.services.shadow_review_service import (
    build_parser_shadow_review_report,
    build_profile_shadow_review_report,
)


def _cleanup_shadow_review_user(session, user_id: str) -> None:
    session.execute(delete(ActionNode).where(ActionNode.user_id == user_id))
    session.execute(delete(EventLog).where(EventLog.user_id == user_id))
    session.commit()


def _persist_shadow_event(
    session,
    *,
    user_id: str,
    comparison_result: str | None,
    created_at: datetime,
    source: str = "frontend_web_shell",
    parse_status: str = "success",
) -> str:
    event_id = uuid4()
    parse_metadata = {"primary": {"provider": "deterministic"}}
    if comparison_result is not None:
        parse_metadata["comparison_result"] = comparison_result
        parse_metadata["shadow"] = {
            "shadow_provider": "gemini_direct",
            "shadow_status": "success" if comparison_result != "shadow_failed" else "failed",
            "shadow_fallback_reason": None if comparison_result != "shadow_failed" else "schema_validation_failed",
        }
    session.add(
        EventLog(
            event_id=event_id,
            user_id=user_id,
            source=source,
            source_event_type="text",
            external_event_id=f"{user_id}-{event_id}",
            payload_hash=f"{user_id}-{event_id}",
            raw_text="shadow review event",
            raw_payload={"text": "shadow review event"},
            parsed_impact={
                "event_summary": "shadow review event",
                "event_type": "chat_update",
                "mental_delta": -20,
                "physical_delta": 0,
                "focus_mode": "tired",
                "tags": ["mental_load"],
                "should_offer_pull_hint": True,
                "confidence": 0.7,
            },
            parse_metadata=parse_metadata,
            parse_status=parse_status,
            occurred_at=created_at,
            ingested_at=created_at,
            created_at=created_at,
        )
    )
    session.commit()
    return str(event_id)


def _persist_shadow_node(
    session,
    *,
    user_id: str,
    title: str,
    comparison_result: str | None,
    updated_at: datetime,
) -> str:
    node_id = uuid4()
    ai_context = {}
    if comparison_result is not None:
        ai_context = {
            "profile_comparison_result": comparison_result,
            "profile_metadata": {
                "primary": {"provider": "deterministic"},
                "shadow": {
                    "shadow_provider": "gemini_direct",
                    "shadow_status": "completed" if comparison_result != "shadow_failed" else "failed",
                    "shadow_fallback_reason": None
                    if comparison_result != "shadow_failed"
                    else "schema_validation_failed",
                },
            },
        }
    session.add(
        ActionNode(
            node_id=node_id,
            user_id=user_id,
            drive_type="project",
            status="active",
            title=title,
            summary="shadow review node",
            tags=["admin", "light"],
            priority_score=80,
            dynamic_urgency_score=80,
            mental_energy_required=35,
            physical_energy_required=20,
            estimated_minutes=15,
            recommended_context_tags=["light_admin"],
            confidence_level="low",
            profiling_status="completed",
            profiled_at=updated_at,
            ai_context=ai_context,
            metadata_={},
            created_at=updated_at - timedelta(minutes=1),
            updated_at=updated_at,
        )
    )
    session.commit()
    return str(node_id)


def test_build_parser_shadow_review_report_summarizes_and_flags_results():
    user_id = f"shadow-parser-{uuid4()}"
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        try:
            exact_id = _persist_shadow_event(
                session,
                user_id=user_id,
                comparison_result="exact_match",
                created_at=now - timedelta(minutes=3),
            )
            drift_id = _persist_shadow_event(
                session,
                user_id=user_id,
                comparison_result="drift",
                created_at=now - timedelta(minutes=2),
            )
            failed_id = _persist_shadow_event(
                session,
                user_id=user_id,
                comparison_result="shadow_failed",
                created_at=now - timedelta(minutes=1),
            )
            _persist_shadow_event(
                session,
                user_id=user_id,
                comparison_result=None,
                created_at=now,
            )

            report = build_parser_shadow_review_report(session, user_id=user_id, limit=10)

            assert report["total_events_scanned"] == 4
            assert report["total_compared"] == 3
            assert report["comparison_summary"]["exact_match"] == 1
            assert report["comparison_summary"]["drift"] == 1
            assert report["comparison_summary"]["shadow_failed"] == 1
            assert len(report["flagged_events"]) == 2
            flagged_ids = {item["event_id"] for item in report["flagged_events"]}
            assert drift_id in flagged_ids
            assert failed_id in flagged_ids
            assert exact_id not in flagged_ids
        finally:
            _cleanup_shadow_review_user(session, user_id)


def test_build_profile_shadow_review_report_summarizes_and_flags_results():
    user_id = f"shadow-profile-{uuid4()}"
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        try:
            exact_id = _persist_shadow_node(
                session,
                user_id=user_id,
                title="Exact profile node",
                comparison_result="exact_match",
                updated_at=now - timedelta(minutes=3),
            )
            drift_id = _persist_shadow_node(
                session,
                user_id=user_id,
                title="Drift profile node",
                comparison_result="drift",
                updated_at=now - timedelta(minutes=2),
            )
            failed_id = _persist_shadow_node(
                session,
                user_id=user_id,
                title="Failed profile node",
                comparison_result="shadow_failed",
                updated_at=now - timedelta(minutes=1),
            )
            _persist_shadow_node(
                session,
                user_id=user_id,
                title="Uncompared profile node",
                comparison_result=None,
                updated_at=now,
            )

            report = build_profile_shadow_review_report(session, user_id=user_id, limit=10)

            assert report["total_nodes_scanned"] == 4
            assert report["total_compared"] == 3
            assert report["comparison_summary"]["exact_match"] == 1
            assert report["comparison_summary"]["drift"] == 1
            assert report["comparison_summary"]["shadow_failed"] == 1
            assert len(report["flagged_nodes"]) == 2
            flagged_ids = {item["node_id"] for item in report["flagged_nodes"]}
            assert drift_id in flagged_ids
            assert failed_id in flagged_ids
            assert exact_id not in flagged_ids
        finally:
            _cleanup_shadow_review_user(session, user_id)
