"""Dry-run rebuild of the authoritative user-state snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.replay_service import build_rebuild_state_report

settings = get_settings()


def _parse_iso_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {value}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run rebuild of user_state from authoritative history.")
    parser.add_argument("--user-id", default=settings.default_user_id, help="Target user_id.")
    parser.add_argument("--from-state-history-id", type=int, help="Explicit state_history row to use as anchor.")
    parser.add_argument("--from-created-at", type=_parse_iso_datetime, help="Use the latest checkpoint at or before this timestamp.")
    parser.add_argument("--to-created-at", type=_parse_iso_datetime, help="Stop replaying at or before this timestamp.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    args = parser.parse_args()
    if args.from_state_history_id is not None and args.from_created_at is not None:
        parser.error("--from-state-history-id and --from-created-at cannot be used together")
    return args


def _print_section(title: str, payload: object) -> None:
    print(f"{title}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    with SessionLocal() as session:
        report = build_rebuild_state_report(
            session,
            user_id=args.user_id,
            from_state_history_id=args.from_state_history_id,
            from_created_at=args.from_created_at,
            to_created_at=args.to_created_at,
        )

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
        return 0

    print(f"User ID: {report['user_id']}")
    print(f"Summary status: {report['summary_status']}")
    print(f"Replayed event count: {report['replayed_event_count']}")
    _print_section("Anchor", report["anchor"])
    _print_section("Comparison target", report["comparison_target"])
    _print_section("Rebuilt state", report["rebuilt_state"])
    _print_section("Current persisted state", report["current_persisted_state"])
    _print_section("Top-level diff", report["top_level_diff"])
    _print_section("Drift events", report["drift_events"])
    _print_section("Event stats", report["event_stats"])
    _print_section("Shadow comparison summary", report["shadow_comparison_summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
