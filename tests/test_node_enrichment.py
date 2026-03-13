from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation
from app.services.annotation_service import (
    SYSTEM_ANNOTATION_SOURCE,
    SYSTEM_ANNOTATION_TYPE,
    enrich_active_nodes,
)

settings = get_settings()


def test_enrich_active_nodes_creates_system_annotations_for_active_nodes():
    active_node_id = uuid4()
    paused_node_id = uuid4()

    with SessionLocal() as session:
        session.add_all(
            [
                ActionNode(
                    node_id=active_node_id,
                    user_id=settings.default_user_id,
                    drive_type="project",
                    status="active",
                    title="Urgent integration cleanup",
                    dynamic_urgency_score=85,
                    ddl_timestamp=datetime.now(timezone.utc) + timedelta(hours=12),
                    recommended_context_tags=["deep_focus"],
                ),
                ActionNode(
                    node_id=paused_node_id,
                    user_id=settings.default_user_id,
                    drive_type="project",
                    status="paused",
                    title="Paused node should not be enriched",
                ),
            ]
        )
        session.commit()

        try:
            result = enrich_active_nodes(session)
            assert result["status"] == "completed"
            assert result["enriched_count"] >= 1

            active_annotation = session.scalar(
                select(NodeAnnotation).where(
                    NodeAnnotation.node_id == active_node_id,
                    NodeAnnotation.source == SYSTEM_ANNOTATION_SOURCE,
                    NodeAnnotation.annotation_type == SYSTEM_ANNOTATION_TYPE,
                )
            )
            paused_annotation = session.scalar(
                select(NodeAnnotation).where(
                    NodeAnnotation.node_id == paused_node_id,
                    NodeAnnotation.source == SYSTEM_ANNOTATION_SOURCE,
                    NodeAnnotation.annotation_type == SYSTEM_ANNOTATION_TYPE,
                )
            )

            assert active_annotation is not None
            assert active_annotation.fetch_status == "success"
            assert active_annotation.expires_at is not None
            assert active_annotation.freshness_score >= 60
            assert "hint" in active_annotation.content
            assert paused_annotation is None
        finally:
            session.rollback()
            session.execute(delete(NodeAnnotation).where(NodeAnnotation.node_id.in_([active_node_id, paused_node_id])))
            session.execute(delete(ActionNode).where(ActionNode.node_id.in_([active_node_id, paused_node_id])))
            session.commit()


def test_enrich_active_nodes_replaces_existing_system_annotation():
    node_id = uuid4()

    with SessionLocal() as session:
        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="value",
                status="active",
                title="Walk and recover",
                recommended_context_tags=["movement"],
            )
        )
        session.commit()
        session.add(
            NodeAnnotation(
                node_id=node_id,
                annotation_type=SYSTEM_ANNOTATION_TYPE,
                source=SYSTEM_ANNOTATION_SOURCE,
                content={"hint": "old"},
                freshness_score=10,
                fetched_at=datetime.now(timezone.utc) - timedelta(days=2),
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                fetch_status="expired",
            )
        )
        session.commit()

        try:
            enrich_active_nodes(session)
            annotations = session.scalars(
                select(NodeAnnotation).where(
                    NodeAnnotation.node_id == node_id,
                    NodeAnnotation.source == SYSTEM_ANNOTATION_SOURCE,
                    NodeAnnotation.annotation_type == SYSTEM_ANNOTATION_TYPE,
                )
            ).all()

            assert len(annotations) == 1
            assert annotations[0].content["hint"] != "old"
            assert annotations[0].fetch_status == "success"
        finally:
            session.rollback()
            session.execute(delete(NodeAnnotation).where(NodeAnnotation.node_id == node_id))
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()
