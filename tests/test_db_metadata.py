from app.db.base import Base


def test_metadata_contains_core_tables():
    expected_tables = {
        "user_state",
        "state_history",
        "action_nodes",
        "node_annotations",
        "event_logs",
        "recommendation_records",
        "recommendation_feedback",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())
