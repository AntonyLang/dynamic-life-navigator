from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.action_node import ActionNode
from app.services.dynamic_score_service import recalc_dynamic_scores

settings = get_settings()


def test_recalc_dynamic_scores_prioritizes_deadline_urgency():
    node_id = uuid4()

    with SessionLocal() as session:
        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="project",
                status="active",
                title="Submit the urgent report",
                dynamic_urgency_score=0,
                ddl_timestamp=datetime.now(timezone.utc) + timedelta(hours=6),
            )
        )
        session.commit()

        try:
            result = recalc_dynamic_scores(session)
            assert result["status"] == "completed"

            node = session.get(ActionNode, node_id)
            assert node.dynamic_urgency_score >= 90
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_recalc_dynamic_scores_boosts_stale_nodes_without_deadline():
    node_id = uuid4()

    with SessionLocal() as session:
        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="value",
                status="active",
                title="Reconnect with long-term value",
                dynamic_urgency_score=0,
                last_recommended_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
        )
        session.commit()

        try:
            result = recalc_dynamic_scores(session)
            assert result["status"] == "completed"

            node = session.get(ActionNode, node_id)
            assert 15 <= node.dynamic_urgency_score <= 25
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()
