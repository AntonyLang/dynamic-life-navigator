"""Top-level brief route aligned with the PM contract."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id_from_request
from app.db.session import get_db_session
from app.schemas.recommendations import RecommendationBriefResponse
from app.services.brief_service import get_brief

router = APIRouter(tags=["brief"])


@router.get("/brief", response_model=RecommendationBriefResponse, status_code=status.HTTP_200_OK)
def get_brief_route(
    request: Request,
    db: Session = Depends(get_db_session),
) -> RecommendationBriefResponse:
    """Return the brief summary through the top-level PM endpoint."""

    return get_brief(db, get_request_id_from_request(request))
