"""Offline tests for handoff hot-slot pressure.

Run: python3 test_handoff_pinning_offline.py

Both handoff writers used to hardcode priority=3, pinned=True, so every
handoff ever written held a hot slot permanently. On a 50-slot board that
meant 33 handoffs, 17 of them pinned. Only the newest handoff per agent is
a live instruction; the rest are history.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="handoffpin-"))
os.environ["AGENT_PROJECT_DIR"] = str(_TMP)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server as S  # noqa: E402


def _handoff(eid, agent, pinned=True, priority=3):
    return {"id": eid, "agent_name": agent, "memory_type": S.MemoryType.HANDOFF,
            "title": f"Handoff from {agent}", "content": "c", "tags": ["handoff"],
            "priority": priority, "pinned": pinned,
            "created_at": "2026-08-01T00:00:00+07:00", "timestamp": time.time()}


def test_a_new_handoff_supersedes_the_authors_earlier_ones():
    mem = [_handoff("h1", "alice"), _handoff("h2", "alice")]
    assert S._demote_prior_handoffs(mem, "alice", "alice") == 2
    assert all(not m["pinned"] for m in mem)
    assert all(m["priority"] == 1 for m in mem)


def test_other_agents_handoffs_are_untouched():
    """One agent leaving does not invalidate another agent's instructions."""
    mine, theirs = _handoff("h1", "alice"), _handoff("h2", "bob")
    assert S._demote_prior_handoffs([mine, theirs], "alice", "alice") == 1
    assert theirs["pinned"] is True and theirs["priority"] == 3


def test_demotion_carries_the_audit_trail():
    h = _handoff("h1", "alice")
    S._demote_prior_handoffs([h], "alice", "alice")
    assert h["unpinned_by"] == "alice"
    assert h["unpin_reason"] == "superseded by a newer handoff"
    assert "pinned_summary" not in h


def test_non_handoff_entries_are_never_touched():
    """Keyed on memory_type, not on the agent alone."""
    note = {"id": "n1", "agent_name": "alice", "memory_type": "decision",
            "title": "t", "content": "c", "priority": 3, "pinned": True}
    assert S._demote_prior_handoffs([note], "alice", "alice") == 0
    assert note["pinned"] is True


def test_already_demoted_handoffs_are_not_re_stamped():
    """Idempotent: a second pass must not overwrite the original audit."""
    h = _handoff("h1", "alice")
    S._demote_prior_handoffs([h], "alice", "alice")
    first = h["unpinned_at"]
    assert S._demote_prior_handoffs([h], "alice", "bob") == 0
    assert h["unpinned_by"] == "alice" and h["unpinned_at"] == first


def test_the_board_keeps_one_pinned_handoff_per_agent():
    """The property that actually frees hot slots."""
    mem = []
    for agent in ("alice", "bob"):
        for i in range(5):
            S._demote_prior_handoffs(mem, agent, agent)
            mem.append(_handoff(f"{agent}{i}", agent))
    pinned = [m for m in mem if m["pinned"]]
    assert len(mem) == 10
    assert len(pinned) == 2
    assert {m["id"] for m in pinned} == {"alice4", "bob4"}


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
