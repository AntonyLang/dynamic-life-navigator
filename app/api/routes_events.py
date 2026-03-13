"""Top-level event ingestion routes aligned with the PM contract."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id_from_request
from app.db.session import get_db_session
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.event_ingestion import ingest_chat_message

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest", response_model=ChatMessageResponse, status_code=status.HTTP_200_OK)
def post_event_ingest(
    payload: ChatMessageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> ChatMessageResponse:
    """Accept the MVP primary input through a stable event-ingest endpoint."""

    return ingest_chat_message(db, get_request_id_from_request(request), payload, background_tasks=background_tasks)
