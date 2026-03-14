"""Summarize recent profile shadow comparison drift for operator review."""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.shadow_review_service import build_profile_shadow_review_report

settings = get_settings()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show recent profile shadow comparison results.")
    parser.add_argument("--user-id", default=settings.default_user_id, help="Target user_id.")
    parser.add_argument("--limit", type=int, default=50, help="Number of recent nodes to scan.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    return parser.parse_args()


def _print_section(title: str, payload: object) -> None:
    print(f"{title}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    with SessionLocal() as session:
        report = build_profile_shadow_review_report(session, user_id=args.user_id, limit=args.limit)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
        return 0

    print(f"User ID: {report['user_id']}")
    print(f"Nodes scanned: {report['total_nodes_scanned']}")
    print(f"Nodes compared: {report['total_compared']}")
    _print_section("Comparison summary", report["comparison_summary"])
    _print_section("Flagged nodes", report["flagged_nodes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
