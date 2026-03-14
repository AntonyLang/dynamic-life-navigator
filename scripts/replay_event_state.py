"""Replay one persisted event through the authoritative state reducer."""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services.replay_service import build_event_replay_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay one persisted event against recorded state history.")
    parser.add_argument("event_id", help="Persisted event_id to replay.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    return parser.parse_args()


def _print_section(title: str, payload: object) -> None:
    print(f"{title}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    with SessionLocal() as session:
        report = build_event_replay_report(session, args.event_id)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
        return 0

    print(f"Event ID: {report['event']['event_id']}")
    print(f"Replay result: {report['replay_result']}")
    print(f"Parse status: {report['event']['parse_status']}")
    if report.get("state_history"):
        print(f"State history ID: {report['state_history']['state_history_id']}")
    _print_section("Authoritative parsed impact", report["authoritative_parsed_impact"])
    _print_section("Parse metadata", report["parse_metadata"])
    _print_section("Recorded before state", report["recorded_before_state"])
    _print_section("Recorded after state", report["recorded_after_state"])
    _print_section("Recomputed after state", report["recomputed_after_state"])
    _print_section("Top-level diff", report["top_level_diff"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
