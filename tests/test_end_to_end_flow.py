from __future__ import annotations

from datetime import datetime, timezone
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.action_node import ActionNode
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.models.user_state import UserState
from app.services.gemini_direct_parser import GeminiDirectEventParserProvider
from app.services.openai_responses_parser import OpenAIResponsesEventParserProvider
from app.services.event_processing import apply_state_patch_from_event, parse_event_log
from app.services import event_ingestion
from app.workers.local_pipeline import run_local_event_pipeline

settings = get_settings()


def test_ingest_parse_state_and_recommendation_flow(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    client_message_id = f"e2e-{uuid4()}"
    node_id = uuid4()
    node_title = f"Take a small recovery walk {str(node_id)[:8]}"
    recommendation_id = None
    event_id = None

    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", True, raising=False)

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        original_state = user_state_guard
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="project",
                status="active",
                title=node_title,
                priority_score=95,
                dynamic_urgency_score=95,
                mental_energy_required=10,
                physical_energy_required=10,
                confidence_level="medium",
            )
        )
        session.commit()

        try:
            monkeypatch.setattr(event_ingestion.parse_event_log, "delay", lambda event_id: None)
            ingest_response = client.post(
                "/api/v1/events/ingest",
                json={
                    "channel": "desktop_plugin",
                    "message_type": "text",
                    "text": "I am drained after debugging all afternoon.",
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:00:00+08:00",
                },
            )
            assert ingest_response.status_code == 200
            event_id = UUID(ingest_response.json()["event_id"])

            parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            assert snapshot.focus_mode == "tired"

            recommendation_response = client.get("/api/v1/recommendations/next?limit=1")
            assert recommendation_response.status_code == 200
            body = recommendation_response.json()
            recommendation_id = UUID(body["recommendation_id"])

            assert body["empty_state"] is False
            assert body["items"][0]["title"] == node_title

            session.expire_all()
            refreshed_state = session.get(UserState, settings.default_user_id)
            assert refreshed_state is not None
            assert refreshed_state.source_last_event_id == event_id
            assert refreshed_state.state_version == original_state["state_version"] + 1
        finally:
            if recommendation_id is not None:
                session.execute(
                    delete(RecommendationFeedback).where(
                        RecommendationFeedback.recommendation_id == recommendation_id
                    )
                )
                session.execute(
                    delete(RecommendationRecord).where(
                        RecommendationRecord.recommendation_id == recommendation_id
                    )
                )
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_chat_message_route_advances_state_via_local_background_pipeline(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-local-pipeline-{uuid4()}"
    event_id = None
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", False, raising=False)

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        original_state = user_state_guard
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()
        baseline_state_version = state.state_version

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:00:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
            assert state_body["recent_context"] == zh_text

            session.expire_all()
            refreshed_state = session.get(UserState, settings.default_user_id)
            assert refreshed_state is not None
            assert refreshed_state.source_last_event_id == event_id
            assert refreshed_state.state_version >= baseline_state_version + 1
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()


def test_chat_message_route_advances_state_via_worker_dispatch_path_with_chinese_input(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-worker-dispatch-{uuid4()}"
    event_id = None
    queued_event_ids: list[str] = []
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", True, raising=False)
    monkeypatch.setattr(event_ingestion.parse_event_log, "delay", lambda event_id: queued_event_ids.append(event_id))

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()
        baseline_state_version = state.state_version

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:05:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])
            assert queued_event_ids == [str(event_id)]

            run_local_event_pipeline(str(event_id))

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
            assert state_body["recent_context"] == zh_text

            session.expire_all()
            refreshed_state = session.get(UserState, settings.default_user_id)
            assert refreshed_state is not None
            assert refreshed_state.source_last_event_id == event_id
            assert refreshed_state.state_version >= baseline_state_version + 1
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()


def test_chat_message_route_advances_state_via_structured_stub_worker_off(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-structured-stub-off-{uuid4()}"
    event_id = None
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setenv("PARSER_PROVIDER", "structured_stub")
    get_settings.cache_clear()
    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", False, raising=False)

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:10:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()
            get_settings.cache_clear()


def test_chat_message_route_advances_state_via_structured_stub_worker_dispatch(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-structured-stub-on-{uuid4()}"
    event_id = None
    queued_event_ids: list[str] = []
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setenv("PARSER_PROVIDER", "structured_stub")
    get_settings.cache_clear()
    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", True, raising=False)
    monkeypatch.setattr(event_ingestion.parse_event_log, "delay", lambda event_id: queued_event_ids.append(event_id))

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:15:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])
            assert queued_event_ids == [str(event_id)]

            run_local_event_pipeline(str(event_id))

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()
            get_settings.cache_clear()


def test_chat_message_route_advances_state_via_structured_model_shell_worker_off(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-structured-model-shell-{uuid4()}"
    event_id = None
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setenv("PARSER_PROVIDER", "structured_model_shell")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "demo-model")
    get_settings.cache_clear()
    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", False, raising=False)

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:20:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()
            get_settings.cache_clear()


def test_chat_message_route_advances_state_via_openai_responses_worker_off(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-openai-responses-{uuid4()}"
    event_id = None
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setenv("PARSER_PROVIDER", "openai_responses")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "gpt-5.4-mini")
    get_settings.cache_clear()
    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", False, raising=False)
    monkeypatch.setattr(
        OpenAIResponsesEventParserProvider,
        "_post_responses_request",
        lambda self, _payload: {
            "output_text": '{"status":"success","impact":{"event_summary":"\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002","event_type":"chat_update","mental_delta":-20,"physical_delta":0,"focus_mode":"tired","tags":["mental_load"],"should_offer_pull_hint":true,"confidence":0.7}}'
        },
    )

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:25:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()
            get_settings.cache_clear()


def test_chat_message_route_advances_state_via_gemini_direct_worker_off(
    monkeypatch,
    cleanup_db_artifacts,
    user_state_guard,
):
    client = TestClient(app)
    client_message_id = f"e2e-gemini-direct-{uuid4()}"
    event_id = None
    zh_text = "\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002"

    monkeypatch.setenv("PARSER_PROVIDER", "gemini_direct")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("STRUCTURED_PARSER_MODEL_NAME", "gemini-2.5-flash")
    get_settings.cache_clear()
    monkeypatch.setattr(event_ingestion.settings, "enable_worker_dispatch", False, raising=False)
    monkeypatch.setattr(
        GeminiDirectEventParserProvider,
        "_post_generate_content_request",
        lambda self, _payload: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"status":"success","impact":{"event_summary":"\u521a\u505a\u5b8c\u5f88\u91cd\u7684\u8111\u529b\u6d3b\uff0c\u60f3\u5148\u7f13\u4e00\u4e0b\u3002","event_type":"chat_update","mental_delta":-20,"physical_delta":0,"focus_mode":"tired","tags":["mental_load"],"should_offer_pull_hint":true,"confidence":0.7}}'
                            }
                        ]
                    }
                }
            ]
        },
    )

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        state.mental_energy = 85
        state.physical_energy = 85
        state.focus_mode = "recovered"
        state.recent_context = "integration baseline"
        state.updated_at = datetime.now(timezone.utc)
        state.source_last_event_id = None
        state.source_last_event_at = None
        session.add(state)
        session.commit()

        try:
            response = client.post(
                "/api/v1/chat/messages",
                json={
                    "channel": "frontend_web_shell",
                    "message_type": "text",
                    "text": zh_text,
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:30:00+08:00",
                },
            )
            assert response.status_code == 200
            event_id = UUID(response.json()["event_id"])

            state_body = None
            for _ in range(6):
                state_response = client.get("/api/v1/state")
                assert state_response.status_code == 200
                state_body = state_response.json()["state"]
                if state_body["recent_context"] == zh_text:
                    break
                time.sleep(0.25)

            assert state_body is not None
            assert state_body["focus_mode"] == "tired"
            assert state_body["mental_energy"] == 65
        finally:
            if event_id is not None:
                cleanup_db_artifacts.event_ids(event_id)
            session.commit()
            get_settings.cache_clear()
