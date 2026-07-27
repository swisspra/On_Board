"""Blocking wait primitive for On Board (pure, testable).

WHY THIS EXISTS
    On Board is pull-only. An agent learns that a peer created a ticket or
    left a handoff only when a human tells it to look, which makes the human
    the message pump. This module supplies the missing edge: an agent parks
    inside one tool call and returns when the board actually changes.

CONSTRAINTS THAT SHAPED IT
    * Claude Desktop hard-cancels MCP tool calls at ~240s. The cap is not
      configurable and repeated cancellations wedge every connected server
      until restart, so timeout_s is clamped well below it by default.
      Claude Code over stdio has no per-request timer and may pass more.
    * The scarce resource is human pokes, not tokens. Two consequences:
      CHECK BEFORE BLOCKING, so a re-arm after a long gap returns its backlog
      instantly, and DRAIN, so one wake returns every pending event rather
      than the first.
    * A parked agent issues no tool calls, so a peer's _lazy_kia_sweep would
      mark it KIA mid-wait. The caller injects heartbeat_fn and we fire it on
      every tick.
    * An agent must never wake on its own action. Self-authored events are
      dropped before they reach the caller. That is the loop guard, and it is
      a capability boundary rather than a tunable budget.

PURITY
    No imports from server.py and no file I/O. The caller injects snapshot_fn
    and heartbeat_fn, which keeps this unit-testable offline. Same posture as
    the pure rule modules in earlier ticket brokers.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Iterable, Optional

# --- event kinds ---------------------------------------------------------

TICKET_CREATED = "ticket_created"
TICKET_STATUS_CHANGED = "ticket_status_changed"
TICKET_ASSIGNED = "ticket_assigned"
MEMORY_WRITTEN = "memory_written"

ALL_KINDS = frozenset({
    TICKET_CREATED, TICKET_STATUS_CHANGED, TICKET_ASSIGNED, MEMORY_WRITTEN,
})

# The events that usually mean "your turn". memory_written is opt-in because
# checkpoints fire constantly and would wake a listener on noise.
DEFAULT_KINDS = (TICKET_CREATED, TICKET_STATUS_CHANGED, TICKET_ASSIGNED)

# --- timeout policy ------------------------------------------------------

DEFAULT_TIMEOUT_S = 180
DESKTOP_SAFE_MAX_S = 200     # stay clear of Desktop's ~240s cancel
HARD_MAX_S = 3600            # stdio callers (Claude Code) may park far longer
DEFAULT_POLL_INTERVAL_S = 2.0


def clamp_timeout(timeout_s: Any, *, desktop_safe: bool = True) -> int:
    """Clamp a requested wait to something the client can actually survive.

    desktop_safe=True (default) keeps the call under Claude Desktop's ~240s
    cancel. Callers on a stdio transport (Claude Code) may pass False and park
    for much longer, since stdio has no per-request timer.
    """
    try:
        t = int(timeout_s)
    except (TypeError, ValueError):
        t = DEFAULT_TIMEOUT_S
    ceiling = DESKTOP_SAFE_MAX_S if desktop_safe else HARD_MAX_S
    return max(1, min(t, ceiling))


def normalize_kinds(kinds: Optional[Iterable[str]]) -> frozenset:
    """Validate a requested kind filter, falling back to the default set."""
    if not kinds:
        return frozenset(DEFAULT_KINDS)
    picked = frozenset(k for k in kinds if k in ALL_KINDS)
    return picked or frozenset(DEFAULT_KINDS)


# --- snapshot diffing ----------------------------------------------------
# A snapshot is {"tickets": {id: ticket_dict}, "memories": {id: memory_dict}}.
# Both sub-dicts are keyed by id so the diff is a plain key/field comparison
# and never depends on list ordering.

# Fields the ticket tools stamp with whoever performed each transition.
# Carried onto every event so attribution is read, not guessed.
ACTOR_FIELDS = ("created_by", "assigned_to", "claimed_by", "submitted_by",
                "reviewed_by", "canceled_by", "terminated_by")

# Verified live 2026-07-26: a listener woken by an approve received only
# "submitted -> closed" and had to infer the outcome. On a REJECTION that is
# materially bad — the worker wakes knowing it failed but not why, which
# defeats the point of it retrying autonomously. Carry the verdict text.
VERDICT_FIELDS = ("review_notes", "fix_instructions", "rejection_count")


def _ticket_event(kind: str, t: dict, **extra) -> dict:
    ev = {
        "kind": kind,
        "ticket_id": t.get("id"),
        "title": t.get("title"),
        "status": t.get("status"),
        "priority": t.get("priority"),
        "at": t.get("updated_at") or t.get("created_at"),
    }
    for f in ACTOR_FIELDS + VERDICT_FIELDS:
        ev[f] = t.get(f)
    ev.update(extra)
    return ev


def diff_tickets(prev: dict, cur: dict) -> list:
    """Yield ticket events between two index snapshots keyed by ticket id."""
    events = []
    for tid, t in cur.items():
        old = prev.get(tid)
        if old is None:
            events.append(_ticket_event(TICKET_CREATED, t))
            continue
        if old.get("status") != t.get("status"):
            events.append(_ticket_event(
                TICKET_STATUS_CHANGED, t,
                previous_status=old.get("status"),
                previous_rejection_count=old.get("rejection_count"),
            ))
        if old.get("assigned_to") != t.get("assigned_to"):
            events.append(_ticket_event(
                TICKET_ASSIGNED, t,
                previous_assignee=old.get("assigned_to"),
            ))
    return events


def diff_memories(prev: dict, cur: dict) -> list:
    """Yield an event per newly written memory entry."""
    events = []
    for mid, m in cur.items():
        if mid in prev:
            continue
        events.append({
            "kind": MEMORY_WRITTEN,
            "memory_id": mid,
            "type": m.get("type"),
            "title": m.get("title"),
            "agent_name": m.get("agent_name"),
            "at": m.get("timestamp") or m.get("created_at"),
        })
    return events


# --- relevance + the loop guard ------------------------------------------
# Attribution is read from the field each ticket tool stamps with the acting
# agent. The WORKER_DRIVEN / OWNER_DRIVEN sets below survive only as a
# fallback for tickets written before those fields existed, since an upgraded
# server still has to read whatever is already in .agent-mem/.

# status the ticket landed in -> field naming who put it there
_ACTOR_FIELD_BY_STATUS = {
    "open": "created_by",
    "claimed": "claimed_by",
    "in_progress": "claimed_by",
    "creating_report": "claimed_by",
    "submitted": "submitted_by",
    "reviewing": "reviewed_by",
    "in_review": "reviewed_by",
    "closed": "reviewed_by",
    "rejected": "reviewed_by",
    "canceled": "canceled_by",
    "terminated": "terminated_by",
}

WORKER_DRIVEN = frozenset({"claimed", "in_progress", "creating_report", "submitted"})
OWNER_DRIVEN = frozenset({"reviewing", "in_review", "closed", "canceled",
                          "terminated", "rejected"})


def rejection_happened(ev: dict) -> bool:
    """True when this status change IS a rejection landing back on 'open'.

    memory_review_ticket writes REJECTED then immediately reopens to OPEN in
    the same call, so a poller never observes 'rejected'. The only durable
    trace is rejection_count incrementing — presence alone is not enough,
    since the count persists forever and would false-flag any later reopen.
    """
    if ev.get("kind") != TICKET_STATUS_CHANGED:
        return False
    return (ev.get("rejection_count") or 0) > (ev.get("previous_rejection_count") or 0)


def infer_actor(ev: dict) -> Optional[str]:
    """Who caused this event. Exact when the stamp is present, else inferred."""
    kind = ev.get("kind")
    if kind == TICKET_CREATED:
        return ev.get("created_by")
    if kind == MEMORY_WRITTEN:
        return ev.get("agent_name")
    if kind == TICKET_ASSIGNED:
        # No reassign tool exists, so there is nothing to attribute this to.
        # Returning None leaves it unfiltered, which is the safe direction:
        # a spurious wake costs a poke, a suppressed one loses work.
        return None
    if kind == TICKET_STATUS_CHANGED:
        # A reject lands the ticket on 'open', whose map entry is created_by —
        # but the true actor is the REVIEWER. Left uncorrected, a third-party
        # coordinator's reject suppresses the owner (missed wake) and wakes
        # the coordinator on her own action (a hole in the loop guard).
        if rejection_happened(ev):
            return ev.get("reviewed_by")
        status = (ev.get("status") or "").lower()
        stamped = ev.get(_ACTOR_FIELD_BY_STATUS.get(status, ""))
        if stamped:
            return stamped
        if status in WORKER_DRIVEN:
            return ev.get("claimed_by") or ev.get("created_by")
        if status in OWNER_DRIVEN:
            return ev.get("created_by")
    return None


def is_relevant(ev: dict, *, agent_name: Optional[str], only_mine: bool = True) -> bool:
    """Decide whether an event should wake this agent.

    The first check is the loop guard: an agent never wakes on its own action.
    Without it two listeners ping-pong until the usage limit stops them.
    """
    if agent_name and infer_actor(ev) == agent_name:
        return False
    if not only_mine:
        return True
    if ev.get("kind") == MEMORY_WRITTEN:
        return True
    assigned = ev.get("assigned_to")
    if assigned in (None, "", agent_name):
        return True                      # unassigned == the open queue
    return ev.get("created_by") == agent_name   # your ticket, your review


def diff_events(prev: dict, cur: dict, *, agent_name: Optional[str] = None,
                kinds: Optional[Iterable[str]] = None,
                only_mine: bool = True) -> list:
    """Full diff between two snapshots, filtered by kind and relevance."""
    wanted = normalize_kinds(kinds)
    events = []
    events.extend(diff_tickets(prev.get("tickets", {}), cur.get("tickets", {})))
    if MEMORY_WRITTEN in wanted:
        events.extend(diff_memories(prev.get("memories", {}), cur.get("memories", {})))
    return [
        e for e in events
        if e.get("kind") in wanted
        and is_relevant(e, agent_name=agent_name, only_mine=only_mine)
    ]


# --- the wait loop -------------------------------------------------------

async def wait_for_events(
    snapshot_fn: Callable[[], dict],
    *,
    agent_name: Optional[str] = None,
    baseline: Optional[dict] = None,
    kinds: Optional[Iterable[str]] = None,
    only_mine: bool = True,
    timeout_s: Any = DEFAULT_TIMEOUT_S,
    desktop_safe: bool = True,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    heartbeat_fn: Optional[Callable[[], None]] = None,
    sleep_fn: Optional[Callable] = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Park until the board changes, then return every pending event.

    :param snapshot_fn: () -> {"tickets": {...}, "memories": {...}}
    :param baseline: the snapshot this agent last saw. When supplied, the
        backlog accumulated since then is returned WITHOUT blocking — this is
        what makes a re-arm after a 20-minute gap cost one call instead of
        waking empty-handed. When None, the current state becomes the
        baseline and we listen forward from now.
    :param heartbeat_fn: fired every tick so a peer's idle sweep does not
        mark this parked agent KIA.
    :returns: {"status": "hit"|"idle", "events": [...], "snapshot": {...}}
        The caller persists `snapshot` as the next baseline, on both outcomes.
    """
    sleep = sleep_fn or asyncio.sleep
    budget = clamp_timeout(timeout_s, desktop_safe=desktop_safe)
    started = clock()
    deadline = started + budget

    def _beat():
        if heartbeat_fn:
            try:
                heartbeat_fn()
            except Exception:      # never let liveness bookkeeping kill a wait
                pass

    _beat()
    current = snapshot_fn()

    # CHECK BEFORE BLOCKING: drain whatever accrued while we were away.
    if baseline is not None:
        backlog = diff_events(baseline, current, agent_name=agent_name,
                              kinds=kinds, only_mine=only_mine)
        if backlog:
            return {"status": "hit", "events": backlog,
                    "event_count": len(backlog), "waited_s": 0.0,
                    "timeout_s": budget, "snapshot": current,
                    "drained_backlog": True}
    else:
        baseline = current

    while clock() < deadline:
        await sleep(min(poll_interval_s, max(0.0, deadline - clock())))
        _beat()
        current = snapshot_fn()
        events = diff_events(baseline, current, agent_name=agent_name,
                             kinds=kinds, only_mine=only_mine)
        if events:
            return {"status": "hit", "events": events,
                    "event_count": len(events),
                    "waited_s": round(clock() - started, 2),
                    "timeout_s": budget, "snapshot": current,
                    "drained_backlog": False}
        # Advance the baseline so filtered-out churn is not re-diffed forever.
        baseline = current

    return {"status": "idle", "events": [], "event_count": 0,
            "waited_s": round(clock() - started, 2),
            "timeout_s": budget, "snapshot": current,
            "drained_backlog": False}
