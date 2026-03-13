"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, status

from app.core.config import AppSettings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def healthcheck() -> dict[str, str]:
    """Simple liveness probe."""

    return {"status": "ok"}


@router.get("/ready", status_code=status.HTTP_200_OK)
def readiness(settings: AppSettings = Depends(get_settings)) -> dict[str, object]:
    """Conservative readiness probe for the API process itself."""

    return {
        "status": "ready",
        "env": settings.env,
        "checks": {
            "settings_loaded": True,
            "database_connection": "not_checked",
            "redis_connection": "not_checked",
        },
    }
