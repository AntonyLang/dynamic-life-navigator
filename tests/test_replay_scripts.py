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


def test_replay_event_state_help(monkeypatch):
    module = _load_script_module("replay_event_state.py")
    monkeypatch.setattr(sys, "argv", ["replay_event_state.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 0


def test_replay_event_state_json_output(monkeypatch, capsys):
    module = _load_script_module("replay_event_state.py")
    monkeypatch.setattr(module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        module,
        "build_event_replay_report",
        lambda session, event_id: {
            "event": {"event_id": event_id, "parse_status": "success"},
            "authoritative_parsed_impact": {},
            "parse_metadata": {},
            "recorded_before_state": {},
            "recorded_after_state": {},
            "recomputed_after_state": {},
            "top_level_diff": {},
            "replay_result": "exact_match",
        },
    )
    monkeypatch.setattr(sys, "argv", ["replay_event_state.py", "evt-1", "--json"])

    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["replay_result"] == "exact_match"


def test_rebuild_state_snapshot_help(monkeypatch):
    module = _load_script_module("rebuild_state_snapshot.py")
    monkeypatch.setattr(sys, "argv", ["rebuild_state_snapshot.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        module.parse_args()

    assert exc.value.code == 0


def test_rebuild_state_snapshot_json_output(monkeypatch, capsys):
    module = _load_script_module("rebuild_state_snapshot.py")
    monkeypatch.setattr(module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        module,
        "build_rebuild_state_report",
        lambda session, **kwargs: {
            "user_id": kwargs["user_id"],
            "summary_status": "clean",
            "anchor": {"source": "genesis"},
            "replayed_event_count": 0,
            "rebuilt_state": {},
            "current_persisted_state": {},
            "top_level_diff": {},
            "drift_events": [],
            "event_stats": {"parse_failed_count": 0, "unapplied_event_count": 0},
            "shadow_comparison_summary": {},
            "range": {},
        },
    )
    monkeypatch.setattr(sys, "argv", ["rebuild_state_snapshot.py", "--json"])

    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["summary_status"] == "clean"
