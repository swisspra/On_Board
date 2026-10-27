"""Offline tests for the server half of the idle budget (issue #10).

Run: python -m pytest tests/test_idle_budget_offline.py

Covers the minutes -> parks conversion and the watch-cursor round trip,
including cursor files written before idle_count existed. Each test loads its
own copy of server.py under a unique module name against a per-test tmp dir and
restores AGENT_PROJECT_DIR, so the file is safe to collect with the rest of the
suite.
"""

import importlib.util
import json
import os
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SNAP = {"tickets": {}, "memories": {}}


def load_server(tmp_path):
    """Import server.py bound to tmp_path, leaving the environment as we found it."""
    previous_project = os.environ.get("AGENT_PROJECT_DIR")
    previous_backend = os.environ.get("AGENT_MEM_VECTOR_BACKEND")
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = "none"
    try:
        module_name = f"server_idle_budget_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous_project is None:
            os.environ.pop("AGENT_PROJECT_DIR", None)
        else:
            os.environ["AGENT_PROJECT_DIR"] = previous_project
        if previous_backend is None:
            os.environ.pop("AGENT_MEM_VECTOR_BACKEND", None)
        else:
            os.environ["AGENT_MEM_VECTOR_BACKEND"] = previous_backend
    module._ensure()
    return module


def test_minutes_convert_to_whole_parks(tmp_path):
    """The documented case: 15 minutes of patience at a 180s park."""
    server = load_server(tmp_path)
    assert server._idle_budget_idles(15, 180) == 5


def test_partial_park_rounds_up(tmp_path):
    """10 min / 180s is 3.33 parks. Rounding down would cut patience short."""
    server = load_server(tmp_path)
    assert server._idle_budget_idles(10, 180) == 4


def test_budget_shorter_than_one_park_still_allows_one(tmp_path):
    server = load_server(tmp_path)
    assert server._idle_budget_idles(1, 180) == 1


def test_zero_and_none_mean_listen_forever(tmp_path):
    server = load_server(tmp_path)
    assert server._idle_budget_idles(0, 180) is None
    assert server._idle_budget_idles(None, 180) is None
    assert server._idle_budget_idles(-5, 180) is None


def test_cursor_round_trips_the_counter(tmp_path):
    server = load_server(tmp_path)
    server._save_watch("probe", SNAP, idle_count=4)
    assert server._load_watch_idles("probe") == 4
    assert server._load_watch("probe") == SNAP


def test_legacy_cursor_without_idle_count_reads_zero(tmp_path):
    """Pre-#10 cursor files must not need a migration."""
    server = load_server(tmp_path)
    server._watch_p("legacy").write_text(json.dumps({"snapshot": SNAP}))
    assert server._load_watch_idles("legacy") == 0
    assert server._load_watch("legacy") == SNAP


def test_missing_cursor_reads_zero(tmp_path):
    server = load_server(tmp_path)
    assert server._load_watch_idles("never-seen") == 0


def test_corrupt_counter_does_not_raise(tmp_path):
    server = load_server(tmp_path)
    server._watch_p("bad").write_text(json.dumps({"snapshot": SNAP, "idle_count": "lots"}))
    assert server._load_watch_idles("bad") == 0


def test_negative_counter_is_clamped(tmp_path):
    server = load_server(tmp_path)
    server._save_watch("neg", SNAP, idle_count=-3)
    assert server._load_watch_idles("neg") == 0
