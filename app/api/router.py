"""Top-level API router registration."""

from fastapi import APIRouter

from app.api.routes_brief import router as brief_router
from app.api.routes_chat import router as chat_router
from app.api.routes_events import router as events_router
from app.api.routes_nodes import router as nodes_router
from app.api.routes_recommendations import router as recommendations_router
from app.api.routes_state import router as state_router
from app.api.routes_webhooks import router as webhooks_router
from app.core.config import get_settings

settings = get_settings()
api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(brief_router)
api_router.include_router(chat_router)
api_router.include_router(events_router)
api_router.include_router(nodes_router)
api_router.include_router(state_router)
api_router.include_router(webhooks_router)
api_router.include_router(recommendations_router)
