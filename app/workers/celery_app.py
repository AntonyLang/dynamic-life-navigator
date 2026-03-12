"""
Celery application entrypoint for background workers.

Phase 0:
- Defines a Celery instance configured from AppSettings.
- Task registration will be completed in later phases.
"""

from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    """
    Create and configure the Celery application.

    Later phases will:
    - register task modules explicitly
    """

    settings = get_settings()

    app = Celery(
        "dynamic_life_navigator",
        broker=settings.effective_celery_broker_url,
        backend=settings.effective_celery_result_backend,
    )

    return app


celery_app = create_celery_app()

