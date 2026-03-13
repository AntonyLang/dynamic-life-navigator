"""Action node routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.nodes import ActionNodeCreateRequest, ActionNodeCreateResponse
from app.services.node_service import create_action_node
from app.services.request_context import get_request_id_from_request

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("", response_model=ActionNodeCreateResponse, status_code=status.HTTP_200_OK)
def post_action_node(
    payload: ActionNodeCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ActionNodeCreateResponse:
    """Create a new action node with conservative defaults."""

    return create_action_node(db, get_request_id_from_request(request), payload)
