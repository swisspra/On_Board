"""Offline tests for the server half of the idle budget (issue #10).

Run: python3 test_idle_budget_offline.py

Covers the minutes -> parks conversion and the watch-cursor round trip,
including cursor files written before idle_count existed.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="idlebudget-"))
os.environ["AGENT_PROJECT_DIR"] = str(_TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server as S  # noqa: E402

MEM = _TMP / ".agent-mem"
MEM.mkdir(parents=True, exist_ok=True)
SNAP = {"tickets": {}, "memories": {}}


def test_minutes_convert_to_whole_parks():
    """The documented case: 15 minutes of patience at a 180s park."""
    assert S._idle_budget_idles(15, 180) == 5


def test_partial_park_rounds_up():
    """10 min / 180s is 3.33 parks. Rounding down would cut patience short."""
    assert S._idle_budget_idles(10, 180) == 4


def test_budget_shorter_than_one_park_still_allows_one():
    assert S._idle_budget_idles(1, 180) == 1


def test_zero_and_none_mean_listen_forever():
    assert S._idle_budget_idles(0, 180) is None
    assert S._idle_budget_idles(None, 180) is None
    assert S._idle_budget_idles(-5, 180) is None


def test_cursor_round_trips_the_counter():
    S._save_watch("probe", SNAP, idle_count=4)
    assert S._load_watch_idles("probe") == 4
    assert S._load_watch("probe") == SNAP


def test_legacy_cursor_without_idle_count_reads_zero():
    """Pre-#10 cursor files must not need a migration."""
    S._watch_p("legacy").write_text(json.dumps({"snapshot": SNAP}))
    assert S._load_watch_idles("legacy") == 0
    assert S._load_watch("legacy") == SNAP


def test_missing_cursor_reads_zero():
    assert S._load_watch_idles("never-seen") == 0


def test_corrupt_counter_does_not_raise():
    S._watch_p("bad").write_text(json.dumps({"snapshot": SNAP, "idle_count": "lots"}))
    assert S._load_watch_idles("bad") == 0


def test_negative_counter_is_clamped():
    S._save_watch("neg", SNAP, idle_count=-3)
    assert S._load_watch_idles("neg") == 0


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failed.append(name)
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
