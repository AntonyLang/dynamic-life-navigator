"""Inspect recent push delivery attempts from the local database."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.push_delivery_attempt import PushDeliveryAttempt
from app.models.recommendation_record import RecommendationRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show recent push delivery attempts.")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent attempts to show.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        rows = session.execute(
            select(PushDeliveryAttempt, RecommendationRecord)
            .join(
                RecommendationRecord,
                RecommendationRecord.recommendation_id == PushDeliveryAttempt.recommendation_id,
            )
            .order_by(PushDeliveryAttempt.created_at.desc())
            .limit(args.limit)
        ).all()

    for attempt, recommendation in rows:
        print(
            json.dumps(
                {
                    "attempt_id": str(attempt.attempt_id),
                    "recommendation_id": str(attempt.recommendation_id),
                    "attempt_number": attempt.attempt_number,
                    "delivery_status": attempt.delivery_status,
                    "response_status_code": attempt.response_status_code,
                    "error_code": attempt.error_code,
                    "created_at": attempt.created_at.isoformat(),
                    "recommendation_mode": recommendation.mode,
                    "recommendation_delivery_status": recommendation.delivery_status,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
