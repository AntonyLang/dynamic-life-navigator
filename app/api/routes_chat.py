"""Chat ingestion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.event_ingestion import ingest_chat_message
from app.services.request_context import get_request_id_from_request

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages", response_model=ChatMessageResponse, status_code=status.HTTP_200_OK)
def post_chat_message(
    payload: ChatMessageRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ChatMessageResponse:
    """Accept a user chat message and return an ack-style response."""

    return ingest_chat_message(db, get_request_id_from_request(request), payload)
