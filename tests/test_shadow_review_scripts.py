from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _load_script_module(script_name: str):
    script_path = PROJECT_ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _DummySession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_show_shadow_parser_drift_help(monkeypatch):
    module = _load_script_module("show_shadow_parser_drift.py")
    monkeypatch.setattr(sys, "argv", ["show_shadow_parser_drift.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 0


def test_show_shadow_parser_drift_json_output(monkeypatch, capsys):
    module = _load_script_module("show_shadow_parser_drift.py")
    monkeypatch.setattr(module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        module,
        "build_parser_shadow_review_report",
        lambda session, **kwargs: {
            "user_id": kwargs["user_id"],
            "limit": kwargs["limit"],
            "total_events_scanned": 3,
            "total_compared": 2,
            "comparison_summary": {
                "exact_match": 1,
                "compatible_match": 0,
                "drift": 1,
                "shadow_failed": 0,
            },
            "flagged_events": [{"event_id": "evt-1", "comparison_result": "drift"}],
        },
    )
    monkeypatch.setattr(sys, "argv", ["show_shadow_parser_drift.py", "--json"])

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparison_summary"]["drift"] == 1


def test_show_shadow_profile_drift_help(monkeypatch):
    module = _load_script_module("show_shadow_profile_drift.py")
    monkeypatch.setattr(sys, "argv", ["show_shadow_profile_drift.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 0


def test_show_shadow_profile_drift_json_output(monkeypatch, capsys):
    module = _load_script_module("show_shadow_profile_drift.py")
    monkeypatch.setattr(module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        module,
        "build_profile_shadow_review_report",
        lambda session, **kwargs: {
            "user_id": kwargs["user_id"],
            "limit": kwargs["limit"],
            "total_nodes_scanned": 3,
            "total_compared": 2,
            "comparison_summary": {
                "exact_match": 1,
                "compatible_match": 0,
                "drift": 0,
                "shadow_failed": 1,
            },
            "flagged_nodes": [{"node_id": "node-1", "comparison_result": "shadow_failed"}],
        },
    )
    monkeypatch.setattr(sys, "argv", ["show_shadow_profile_drift.py", "--json"])

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparison_summary"]["shadow_failed"] == 1
