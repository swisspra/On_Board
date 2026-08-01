"""Offline tests for _split_hot_cold overflow ranking.

Run: python3 test_hot_cold_split_offline.py

Regression: the overflow sort ranked on priority before recency, so a
brand-new unpinned priority-0 entry lost its hot slot to week-old
priority>=1 handoffs. That is how a freshly written compaction digest
landed in the cold set and was archived by the memory_compact it was
written for. Reproduced twice on a live board by two different agents.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="hotcold-"))
os.environ["AGENT_PROJECT_DIR"] = str(_TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server as S  # noqa: E402

NOW = time.time()
OLD = NOW - 400 * 3600  # far outside the 24h hot window


def _entry(eid, mtype="context", priority=0, pinned=False, ts=None):
    return {
        "id": eid,
        "agent_name": "t",
        "memory_type": mtype,
        "title": eid,
        "content": "x",
        "priority": priority,
        "pinned": pinned,
        "timestamp": NOW if ts is None else ts,
        "created_at": "2026-08-01T00:00:00+07:00",
    }


def _old_handoffs(n, priority=1):
    return [_entry(f"ho{i}", "handoff", priority=priority, ts=OLD - i) for i in range(n)]


def test_fresh_unpinned_digest_survives_a_board_full_of_old_handoffs():
    """The reported defect. MAX_HOT old handoffs + 1 new digest -> digest stays hot."""
    digest = _entry("digest", "context", priority=0)
    mem = _old_handoffs(S.MAX_HOT_ENTRIES) + [digest]
    hot, cold = S._split_hot_cold(mem)
    assert len(hot) == S.MAX_HOT_ENTRIES
    assert digest in hot, "fresh digest was evicted to cold"
    assert digest not in cold


def test_the_evicted_entry_is_the_oldest_low_value_one():
    """Something still has to go — it should be the stalest handoff, not the new entry."""
    olds = _old_handoffs(S.MAX_HOT_ENTRIES)
    mem = olds + [_entry("digest", "context", priority=0)]
    hot, cold = S._split_hot_cold(mem)
    assert len(cold) == 1
    assert cold[0] is olds[-1], "expected the oldest handoff to be demoted"


def test_pinned_is_never_evicted_by_a_newer_unpinned_entry():
    """Pinned outranks recency — 'always keep pinned' must still hold."""
    pinned = [_entry(f"pin{i}", "decision", priority=3, pinned=True, ts=OLD - i)
              for i in range(S.MAX_HOT_ENTRIES)]
    mem = pinned + [_entry("fresh", "context", priority=0)]
    hot, cold = S._split_hot_cold(mem)
    assert all(p in hot for p in pinned), "a pinned entry was demoted"
    assert cold and cold[0]["id"] == "fresh"


def test_within_the_hot_window_priority_still_orders():
    """Recency gates the tier; priority orders inside it."""
    recent_low = _entry("recent_low", "context", priority=0, ts=NOW - 60)
    recent_high = _entry("recent_high", "warning", priority=2, ts=NOW - 120)
    mem = _old_handoffs(S.MAX_HOT_ENTRIES - 1) + [recent_low, recent_high]
    hot, cold = S._split_hot_cold(mem)
    assert recent_high in hot and recent_low in hot
    assert hot.index(recent_high) < hot.index(recent_low)


def test_under_the_cap_nothing_is_cold():
    mem = _old_handoffs(S.MAX_HOT_ENTRIES - 5)
    hot, cold = S._split_hot_cold(mem)
    assert cold == [] and len(hot) == S.MAX_HOT_ENTRIES - 5


def test_entries_without_timestamp_do_not_crash_or_win():
    """Legacy rows predate the timestamp field; they must sort last, not first."""
    legacy = {"id": "legacy", "agent_name": "t", "memory_type": "context",
              "title": "legacy", "content": "x", "priority": 0, "pinned": False,
              "created_at": "2026-07-01T00:00:00+07:00"}
    mem = _old_handoffs(S.MAX_HOT_ENTRIES) + [legacy]
    hot, cold = S._split_hot_cold(mem)
    assert legacy in cold


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
