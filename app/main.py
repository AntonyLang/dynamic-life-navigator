"""
ASGI entrypoint for the Dynamic Life Navigator backend.

Phase 0:
- Provides a minimal FastAPI application instance.
- Loads environment-based settings but does not yet wire database or routers.
"""

from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Later phases will:
    - initialize database and Redis connections
    - register API routers and middleware
    """

    settings = get_settings()

    app = FastAPI(
        title="Dynamic Life Navigator",
        version="0.0.0",
        debug=settings.debug,
    )

    # Future hooks:
    # - include routers under settings.api_prefix
    # - attach middleware using settings/env

    return app


app = create_app()

