"""Offline tests for a2a_wait — no MCP, no filesystem, no real sleeping.

Run: python3 test_a2a_wait_offline.py

Time is faked, so the whole suite finishes in milliseconds even though it
exercises 180-second waits.
"""

import asyncio
import sys

import a2a_wait as W


# --- fakes ---------------------------------------------------------------

class FakeClock:
    """Monotonic clock that only advances when the fake sleep is awaited."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = 0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, seconds: float):
        self.sleeps += 1
        self.t += max(seconds, 0.001)


class FakeBoard:
    """Stands in for On Board's ticket index + memory store."""

    def __init__(self):
        self.tickets = {}
        self.memories = {}
        self.reads = 0
        self.script = {}          # read-count -> mutation callable

    def ticket(self, tid, *, status="open", created_by="alice",
               assigned_to=None, claimed_by=None, title="t", **extra):
        self.tickets[tid] = {
            "id": tid, "title": title, "status": status,
            "created_by": created_by, "assigned_to": assigned_to,
            "claimed_by": claimed_by, "priority": "medium",
            "updated_at": f"ts-{self.reads}",
        }
        self.tickets[tid].update(extra)
        return self

    def at_read(self, n, fn):
        self.script[n] = fn
        return self

    def snapshot(self):
        if self.reads in self.script:
            self.script.pop(self.reads)(self)
        self.reads += 1
        return {"tickets": {k: dict(v) for k, v in self.tickets.items()},
                "memories": {k: dict(v) for k, v in self.memories.items()}}


# --- timeout policy ------------------------------------------------------

def test_clamp_keeps_desktop_under_the_cancel():
    assert W.clamp_timeout(180) == 180
    assert W.clamp_timeout(600) == W.DESKTOP_SAFE_MAX_S == 200
    assert W.clamp_timeout(600, desktop_safe=False) == 600
    assert W.clamp_timeout(99999, desktop_safe=False) == W.HARD_MAX_S
    assert W.clamp_timeout("nonsense") == W.DEFAULT_TIMEOUT_S
    assert W.clamp_timeout(0) == 1


# --- diffing -------------------------------------------------------------

def test_new_ticket_is_an_event():
    cur = FakeBoard().ticket("T1").snapshot()
    evs = W.diff_events({}, cur, agent_name="bob")
    assert [e["kind"] for e in evs] == [W.TICKET_CREATED]
    assert evs[0]["ticket_id"] == "T1"


def test_status_change_carries_previous_status():
    prev = FakeBoard().ticket("T1", status="claimed", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="submitted", claimed_by="bob").snapshot()
    evs = W.diff_events(prev, cur, agent_name="alice")
    assert len(evs) == 1
    assert evs[0]["kind"] == W.TICKET_STATUS_CHANGED
    assert evs[0]["previous_status"] == "claimed"
    assert evs[0]["status"] == "submitted"


def test_unchanged_board_yields_nothing():
    snap = FakeBoard().ticket("T1").snapshot()
    assert W.diff_events(snap, snap, agent_name="bob") == []


# --- the loop guard ------------------------------------------------------

def test_agent_never_wakes_on_its_own_ticket():
    cur = FakeBoard().ticket("T1", created_by="alice").snapshot()
    assert W.diff_events({}, cur, agent_name="alice") == []
    assert len(W.diff_events({}, cur, agent_name="bob")) == 1


def test_worker_does_not_wake_on_its_own_submission():
    prev = FakeBoard().ticket("T1", status="claimed",
                              created_by="alice", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="submitted",
                             created_by="alice", claimed_by="bob").snapshot()
    assert W.diff_events(prev, cur, agent_name="bob") == []       # bob did it
    assert len(W.diff_events(prev, cur, agent_name="alice")) == 1  # alice reviews


def test_only_mine_ignores_someone_elses_assignment():
    cur = FakeBoard().ticket("T1", created_by="alice",
                             assigned_to="carol").snapshot()
    assert W.diff_events({}, cur, agent_name="bob") == []
    assert len(W.diff_events({}, cur, agent_name="bob", only_mine=False)) == 1
    assert len(W.diff_events({}, cur, agent_name="carol")) == 1


# --- exact attribution beats the heuristic -------------------------------

def _closed_by(actor):
    """alice owns, bob executed, `actor` did the closing."""
    prev = FakeBoard().ticket("T1", status="submitted",
                              created_by="alice", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="closed", created_by="alice",
                             claimed_by="bob", reviewed_by=actor).snapshot()
    return prev, cur


def test_coordinator_close_is_attributed_to_the_coordinator():
    """The heuristic blamed the owner for every close. reviewed_by fixes it."""
    prev, cur = _closed_by("carol")
    assert W.diff_events(prev, cur, agent_name="carol", only_mine=False) == []
    assert len(W.diff_events(prev, cur, agent_name="alice", only_mine=False)) == 1


def test_owner_close_still_suppressed_for_the_owner():
    prev, cur = _closed_by("alice")
    assert W.diff_events(prev, cur, agent_name="alice", only_mine=False) == []


def test_falls_back_to_the_heuristic_on_legacy_tickets():
    """Tickets written before the stamps existed must still be attributable."""
    prev = FakeBoard().ticket("T1", status="submitted",
                              created_by="alice", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="closed",
                             created_by="alice", claimed_by="bob").snapshot()
    assert "reviewed_by" not in [k for k, v in cur["tickets"]["T1"].items() if v]
    assert W.diff_events(prev, cur, agent_name="alice", only_mine=False) == []


def test_submitted_by_attributes_the_submitter():
    prev = FakeBoard().ticket("T1", status="in_progress",
                              created_by="alice", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="submitted", created_by="alice",
                             claimed_by="bob", submitted_by="bob").snapshot()
    assert W.diff_events(prev, cur, agent_name="bob", only_mine=False) == []
    assert len(W.diff_events(prev, cur, agent_name="alice", only_mine=False)) == 1


def test_rejection_carries_the_reason_to_the_listener():
    """Live 2026-07-26: the worker woke knowing it failed but not why."""
    prev = FakeBoard().ticket("T1", status="submitted",
                              created_by="alice", claimed_by="bob").snapshot()
    cur = FakeBoard().ticket("T1", status="rejected", created_by="alice",
                             claimed_by="bob", reviewed_by="alice",
                             review_notes="word count is off by 12",
                             fix_instructions="exclude the frontmatter").snapshot()
    ev = W.diff_events(prev, cur, agent_name="bob", only_mine=False)[0]
    assert ev["review_notes"] == "word count is off by 12"
    assert ev["fix_instructions"] == "exclude the frontmatter"
    assert ev["reviewed_by"] == "alice"


# --- the wait loop -------------------------------------------------------

def _run(board, *, baseline=None, agent="bob", timeout_s=180, beats=None):
    clock = FakeClock()
    res = asyncio.run(W.wait_for_events(
        board.snapshot, agent_name=agent, baseline=baseline,
        timeout_s=timeout_s, poll_interval_s=2.0,
        heartbeat_fn=(lambda: beats.append(1)) if beats is not None else None,
        sleep_fn=clock.sleep, clock=clock,
    ))
    return res, clock


def test_backlog_returns_without_blocking():
    """A re-arm after a long gap must cost one call, not an empty wake."""
    board = FakeBoard().ticket("T1", created_by="alice")
    res, clock = _run(board, baseline={"tickets": {}, "memories": {}})
    assert res["status"] == "hit"
    assert res["drained_backlog"] is True
    assert res["waited_s"] == 0.0
    assert clock.sleeps == 0          # never blocked


def test_one_wake_drains_the_whole_queue():
    board = FakeBoard()
    for n in range(3):
        board.ticket(f"T{n}", created_by="alice")
    res, _ = _run(board, baseline={"tickets": {}, "memories": {}})
    assert res["event_count"] == 3


def test_idle_returns_after_the_budget():
    board = FakeBoard().ticket("T1", created_by="alice")
    res, _ = _run(board, baseline=board.snapshot(), timeout_s=180)
    assert res["status"] == "idle"
    assert res["events"] == []
    assert res["waited_s"] >= 180


def test_wakes_on_a_change_mid_wait():
    board = FakeBoard()
    board.at_read(3, lambda b: b.ticket("T9", created_by="alice"))
    res, _ = _run(board)
    assert res["status"] == "hit"
    assert res["events"][0]["ticket_id"] == "T9"
    assert 0 < res["waited_s"] < 180


def test_heartbeat_fires_every_tick():
    """A parked agent must keep its liveness or a peer sweep marks it KIA."""
    beats = []
    board = FakeBoard().ticket("T1", created_by="alice")
    _run(board, baseline=board.snapshot(), timeout_s=180, beats=beats)
    assert len(beats) > 10


def test_no_baseline_listens_forward_not_backward():
    """First-ever call must not replay the entire existing board."""
    board = FakeBoard().ticket("OLD", created_by="alice")
    board.at_read(2, lambda b: b.ticket("NEW", created_by="alice"))
    res, _ = _run(board, baseline=None)
    assert res["status"] == "hit"
    assert [e["ticket_id"] for e in res["events"]] == ["NEW"]


# --- runner --------------------------------------------------------------

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
