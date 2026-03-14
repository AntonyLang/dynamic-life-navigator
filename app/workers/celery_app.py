"""Celery application entrypoint for background workers."""

from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""

    settings = get_settings()

    app = Celery(
        "dynamic_life_navigator",
        broker=settings.effective_celery_broker_url,
        backend=settings.effective_celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        imports=[
            "app.workers.tasks_compare",
            "app.workers.tasks_parse",
            "app.workers.tasks_profile",
            "app.workers.tasks_scores",
            "app.workers.tasks_state",
            "app.workers.tasks_enrich",
            "app.workers.tasks_compress",
            "app.workers.tasks_push_delivery",
            "app.workers.tasks_push_eval",
        ],
    )

    return app


celery_app = create_celery_app()

# Import task modules so task registration is deterministic during app startup.
from app.workers import tasks_compare as _tasks_compare  # noqa: E402,F401
from app.workers import tasks_compress as _tasks_compress  # noqa: E402,F401
from app.workers import tasks_enrich as _tasks_enrich  # noqa: E402,F401
from app.workers import tasks_parse as _tasks_parse  # noqa: E402,F401
from app.workers import tasks_profile as _tasks_profile  # noqa: E402,F401
from app.workers import tasks_push_delivery as _tasks_push_delivery  # noqa: E402,F401
from app.workers import tasks_push_eval as _tasks_push_eval  # noqa: E402,F401
from app.workers import tasks_scores as _tasks_scores  # noqa: E402,F401
from app.workers import tasks_state as _tasks_state  # noqa: E402,F401
