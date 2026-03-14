from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.parsing import ParserDecisionDTO
from app.services.event_processing import (
    apply_state_patch_from_event,
    compare_shadow_parser_decision,
    parse_event_log,
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


def test_parse_and_apply_state_patch_updates_snapshot(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard
        original_version = original_state["state_version"]
        original_mental = original_state["mental_energy"]
        original_physical = original_state["physical_energy"]

        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="test",
        )

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)

            refreshed_event = session.get(EventLog, event_id)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(
                select(StateHistory)
                .where(StateHistory.event_id == event_id)
                .order_by(StateHistory.created_at.desc())
                .limit(1)
            )

            assert impact["event_type"] == "chat_update"
            assert impact["mental_delta"] < 0
            assert refreshed_event.parse_status == "success"
            assert refreshed_event.parse_metadata["primary"]["provider"] == "deterministic"
            assert snapshot.focus_mode == "tired"
            assert refreshed_state.state_version == original_version + 1
            assert refreshed_state.mental_energy <= original_mental
            assert refreshed_state.physical_energy == original_physical
            assert history is not None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_parse_and_apply_state_patch_supports_chinese_mental_load(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()
    text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    with SessionLocal() as session:
        original_state = user_state_guard

        _persist_event_log(session, event_id=event_id, raw_text=text, external_prefix="zh-mental")

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            refreshed_event = session.get(EventLog, event_id)

            assert impact["event_type"] == "chat_update"
            assert impact["mental_delta"] == -20
            assert refreshed_event.parse_status == "success"
            assert snapshot.focus_mode == "tired"
            assert snapshot.mental_energy == original_state["mental_energy"] - 20
            assert snapshot.recent_context == text
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_parse_supports_chinese_recovery_signal(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="\u521a\u521a\u5348\u7761\u4e86\u4e00\u4f1a\uff0c\u73b0\u5728\u6062\u590d\u4e86\u3002",
            external_prefix="zh-recovery",
        )

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)

            assert impact["event_type"] == "rest"
            assert impact["mental_delta"] == 15
            assert snapshot.focus_mode == "recovered"
            assert snapshot.mental_energy == min(original_state["mental_energy"] + 15, 100)
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_parse_supports_chinese_movement_signal(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="\u521a\u53bb\u6563\u6b65\u4e86\u4e00\u5708\uff0c\u611f\u89c9\u72b6\u6001\u6062\u590d\u4e00\u4e9b\u3002",
            external_prefix="zh-movement",
        )

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)

            assert impact["event_type"] == "exercise"
            assert impact["physical_delta"] == -15
            assert snapshot.focus_mode == "recovered"
            assert snapshot.physical_energy == max(original_state["physical_energy"] - 15, 0)
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_parse_supports_light_admin_and_coordination(cleanup_db_artifacts, user_state_guard):
    light_admin_event_id = uuid4()
    coordination_event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard
        _persist_event_log(
            session,
            event_id=light_admin_event_id,
            raw_text="\u4eca\u665a\u5148\u6574\u7406\u4e00\u4e0b\u90ae\u7bb1\u3002",
            external_prefix="zh-light-admin",
        )
        _persist_event_log(
            session,
            event_id=coordination_event_id,
            raw_text="\u5f85\u4f1a\u8981\u5f00\u4f1a\u540c\u6b65\u65b9\u6848\u3002",
            external_prefix="zh-coordination",
        )

        try:
            light_admin_impact = parse_event_log(session, light_admin_event_id)
            light_admin_snapshot = apply_state_patch_from_event(session, light_admin_event_id)
            session.expire_all()
            coordination_impact = parse_event_log(session, coordination_event_id)
            coordination_snapshot = apply_state_patch_from_event(session, coordination_event_id)

            assert light_admin_impact["event_type"] == "light_admin"
            assert light_admin_snapshot.focus_mode == "light_admin"
            assert light_admin_snapshot.mental_energy == max(original_state["mental_energy"] - 5, 0)

            assert coordination_impact["event_type"] == "coordination"
            assert coordination_snapshot.focus_mode == "social"
            assert coordination_snapshot.physical_energy == light_admin_snapshot.physical_energy
        finally:
            cleanup_db_artifacts.event_ids(light_admin_event_id, coordination_event_id)


def test_parser_prefers_higher_priority_signal(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I feel tired and need a break after debugging.",
            external_prefix="priority",
        )

        try:
            impact = parse_event_log(session, event_id)

            assert impact["event_type"] == "chat_update"
            assert impact["focus_mode"] == "tired"
            assert impact["mental_delta"] == -20
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_fallback_updates_recent_context_without_state_change(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()
    text = "\u4eca\u5929\u968f\u4fbf\u8bb0\u4e00\u4e0b\u5f53\u524d\u60f3\u6cd5\u3002"

    with SessionLocal() as session:
        original_state = user_state_guard
        _persist_event_log(session, event_id=event_id, raw_text=text, external_prefix="fallback")

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            refreshed_event = session.get(EventLog, event_id)

            assert impact["event_type"] == "other"
            assert refreshed_event.parse_status == "fallback"
            assert snapshot.mental_energy == original_state["mental_energy"]
            assert snapshot.physical_energy == original_state["physical_energy"]
            assert snapshot.focus_mode == original_state["focus_mode"]
            assert snapshot.recent_context == text
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_failed_parse_keeps_event_and_skips_state_mutation(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard

        _persist_event_log(session, event_id=event_id, raw_text=None, external_prefix="failed")

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            refreshed_event = session.get(EventLog, event_id)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))

            assert impact == {}
            assert refreshed_event.parse_status == "failed"
            assert snapshot.mental_energy == original_state["mental_energy"]
            assert refreshed_state.state_version == original_state["state_version"]
            assert history is None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_apply_state_patch_retries_on_compare_and_swap_conflict(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        original_state = user_state_guard

        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I feel tired after coding.",
            external_prefix="cas",
        )
        parse_event_log(session, event_id)

        original_execute = session.execute
        call_count = {"updates": 0}

        class DummyResult:
            rowcount = 0

        def execute_once_conflicted(statement, *args, **kwargs):
            if getattr(statement, "table", None) is not None and statement.table.name == "user_state":
                call_count["updates"] += 1
                if call_count["updates"] == 1:
                    return DummyResult()
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", execute_once_conflicted)

        try:
            snapshot = apply_state_patch_from_event(session, event_id, max_retries=3)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))

            assert call_count["updates"] >= 2
            assert snapshot.focus_mode == "tired"
            assert refreshed_state.state_version == original_state["state_version"] + 1
            assert history is not None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_shadow_compare_records_exact_match_without_mutating_state(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    class DummyShadowProvider:
        def parse(self, event):
            return ParserDecisionDTO.model_validate(
                {
                    "status": "success",
                    "impact": {
                        "event_summary": event.raw_text,
                        "event_type": "chat_update",
                        "mental_delta": -20,
                        "physical_delta": 0,
                        "focus_mode": "tired",
                        "tags": ["mental_load"],
                        "should_offer_pull_hint": True,
                        "confidence": 0.7,
                    },
                    "metadata": {
                        "provider": "gemini_direct",
                        "parser_version": "gemini_direct_v1",
                        "prompt_version": "structured_event_parser_prompt_v2",
                        "model_name": "gemini-2.5-flash",
                    },
                }
            )

    with SessionLocal() as session:
        original_state = user_state_guard
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002",
            external_prefix="shadow-exact",
        )

        try:
            parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            monkeypatch.setattr("app.services.event_processing.get_shadow_event_parser_provider", lambda: DummyShadowProvider())

            result = compare_shadow_parser_decision(session, event_id)
            refreshed_event = session.get(EventLog, event_id)
            refreshed_state = session.get(UserState, settings.default_user_id)

            assert result["comparison_result"] == "exact_match"
            assert refreshed_event.parse_metadata["shadow"]["shadow_provider"] == "gemini_direct"
            assert refreshed_event.parse_metadata["comparison_result"] == "exact_match"
            assert refreshed_state.state_version == original_state["state_version"] + 1
            assert snapshot.focus_mode == "tired"
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_shadow_compare_records_compatible_match(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    class DummyShadowProvider:
        def parse(self, event):
            return ParserDecisionDTO.model_validate(
                {
                    "status": "success",
                    "impact": {
                        "event_summary": event.raw_text,
                        "event_type": "chat_update",
                        "mental_delta": -17,
                        "physical_delta": 0,
                        "focus_mode": "tired",
                        "tags": ["mental_load", "recovery_needed"],
                        "should_offer_pull_hint": True,
                        "confidence": 0.8,
                    },
                    "metadata": {
                        "provider": "gemini_direct",
                        "parser_version": "gemini_direct_v1",
                    },
                }
            )

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="shadow-compatible",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            monkeypatch.setattr("app.services.event_processing.get_shadow_event_parser_provider", lambda: DummyShadowProvider())

            result = compare_shadow_parser_decision(session, event_id)
            refreshed_event = session.get(EventLog, event_id)

            assert result["comparison_result"] == "compatible_match"
            assert refreshed_event.parse_metadata["comparison_result"] == "compatible_match"
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_shadow_compare_records_drift(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    class DummyShadowProvider:
        def parse(self, event):
            return ParserDecisionDTO.model_validate(
                {
                    "status": "success",
                    "impact": {
                        "event_summary": event.raw_text,
                        "event_type": "rest",
                        "mental_delta": 15,
                        "physical_delta": 10,
                        "focus_mode": "recovered",
                        "tags": ["recovery"],
                        "should_offer_pull_hint": False,
                        "confidence": 0.7,
                    },
                    "metadata": {
                        "provider": "gemini_direct",
                        "parser_version": "gemini_direct_v1",
                    },
                }
            )

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="shadow-drift",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            monkeypatch.setattr("app.services.event_processing.get_shadow_event_parser_provider", lambda: DummyShadowProvider())

            result = compare_shadow_parser_decision(session, event_id)
            refreshed_event = session.get(EventLog, event_id)

            assert result["comparison_result"] == "drift"
            assert refreshed_event.parse_metadata["comparison_result"] == "drift"
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_shadow_compare_records_shadow_failed_when_provider_falls_back(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    class DummyShadowProvider:
        def parse(self, event):
            return ParserDecisionDTO.model_validate(
                {
                    "status": "success",
                    "impact": {
                        "event_summary": event.raw_text,
                        "event_type": "chat_update",
                        "mental_delta": -20,
                        "physical_delta": 0,
                        "focus_mode": "tired",
                        "tags": ["mental_load"],
                        "should_offer_pull_hint": True,
                        "confidence": 0.7,
                    },
                    "metadata": {
                        "provider": "gemini_direct",
                        "parser_version": "gemini_direct_v1",
                        "fallback_reason": "validation_error_fallback_after_2_attempts",
                        "error_detail": "simulated drift",
                    },
                }
            )

    with SessionLocal() as session:
        _persist_event_log(
            session,
            event_id=event_id,
            raw_text="I am drained after debugging all afternoon.",
            external_prefix="shadow-failed",
        )

        try:
            parse_event_log(session, event_id)
            apply_state_patch_from_event(session, event_id)
            monkeypatch.setattr("app.services.event_processing.get_shadow_event_parser_provider", lambda: DummyShadowProvider())

            result = compare_shadow_parser_decision(session, event_id)
            refreshed_event = session.get(EventLog, event_id)

            assert result["comparison_result"] == "shadow_failed"
            assert refreshed_event.parse_metadata["shadow"]["shadow_fallback_reason"] == "validation_error_fallback_after_2_attempts"
            assert refreshed_event.parse_metadata["comparison_result"] == "shadow_failed"
        finally:
            cleanup_db_artifacts.event_ids(event_id)
