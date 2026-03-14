"""SQLAlchemy declarative base and model registration."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


from app.models.action_node import ActionNode  # noqa: E402,F401
from app.models.event_log import EventLog  # noqa: E402,F401
from app.models.node_annotation import NodeAnnotation  # noqa: E402,F401
from app.models.push_delivery_attempt import PushDeliveryAttempt  # noqa: E402,F401
from app.models.recommendation_feedback import RecommendationFeedback  # noqa: E402,F401
from app.models.recommendation_record import RecommendationRecord  # noqa: E402,F401
from app.models.state_history import StateHistory  # noqa: E402,F401
from app.models.user_state import UserState  # noqa: E402,F401
