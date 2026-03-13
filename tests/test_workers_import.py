from app.workers.celery_app import celery_app


def test_celery_imports_are_registered():
    expected_tasks = {
        "app.workers.parse_event_log",
        "app.workers.apply_state_patch",
        "app.workers.enrich_active_nodes",
        "app.workers.compress_event_logs",
        "app.workers.evaluate_push_opportunities",
    }

    assert expected_tasks.issubset(celery_app.tasks.keys())
