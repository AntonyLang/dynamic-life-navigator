"""State routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id_from_request
from app.db.session import get_db_session
from app.schemas.state import StateResetRequest, StateResetResponse, StateResponse
from app.services.state_service import get_current_state, reset_state

router = APIRouter(prefix="/state", tags=["state"])


@router.get("", response_model=StateResponse, status_code=status.HTTP_200_OK)
def get_state(request: Request, db: Session = Depends(get_db_session)) -> StateResponse:
    """Return the current user state snapshot."""

    return StateResponse(
        request_id=get_request_id_from_request(request),
        state=get_current_state(db),
    )


@router.post("/reset", response_model=StateResetResponse, status_code=status.HTTP_200_OK)
def post_state_reset(
    payload: StateResetRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> StateResetResponse:
    """Reset the user state to explicit values."""

    state = reset_state(db, payload.mental_energy, payload.physical_energy, payload.reason)
    return StateResetResponse(
        request_id=get_request_id_from_request(request),
        state=state,
        reset_reason=payload.reason,
        updated_at=datetime.now(timezone.utc),
    )
