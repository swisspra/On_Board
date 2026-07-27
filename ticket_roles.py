"""Ticket role + ownership rules for On Board (pure, testable).

Ported from a pure ticket-rules module in an earlier broker and widened to On Board's
lifecycle, which has more states because work is claimed from a queue rather
than handed to a single known executor.

    open -> claimed -> in_progress -> creating_report -> submitted
                                                            |
                                        reviewing <---------+
                                          |    |
                              closed <----+    +----> rejected --> in_progress
    canceled / terminated are reachable from most live states.

THE PROPERTY THIS EXISTS TO PROTECT

    completed != success. An agent that DID the work may never adjudicate it.
    Reaching `submitted` is the executor's terminal move; only the ticket's
    owner or a coordinator turns it `closed`.

    This holds even when the executor also happens to be the owner (it created
    the ticket and then claimed it). Solo operation still needs an exit, so
    self-review is possible but must be requested explicitly via
    allow_self_review, and the returned basis records it so the audit shows
    nobody independent looked.

TWO AXES, as in the bridge:

    RELATION  — derived from the ticket. owner = created_by,
                executor = claimed_by. An agent can be both; for adjudication
                the executor role dominates, because that is the conflict.
    ROLE      — coordinator (main/lead/reviewer in On Board's AgentRole)
                may adjudicate and control tickets it neither owns nor
                executed. It is the closest thing to the bridge's `admin`,
                and it is still bound by the self-review rule.

Pure: no imports from server.py, no I/O.
"""

from typing import Optional

STATES = frozenset({
    "open", "claimed", "in_progress", "creating_report", "submitted",
    "reviewing", "in_review", "closed", "rejected", "canceled", "terminated",
})

TERMINAL = frozenset({"closed", "canceled", "terminated"})

# What the executor drives: picking work up and pushing it to submitted.
EXECUTION_TARGETS = frozenset({
    "claimed", "in_progress", "creating_report", "submitted",
})
# What only a disinterested party may drive. The heart of the rule.
ADJUDICATION_TARGETS = frozenset({"reviewing", "in_review", "closed", "rejected"})
# Killing a ticket outright.
CONTROL_TARGETS = frozenset({"canceled", "terminated"})

# Shape of the machine, role-agnostic. Self-transitions where a repeat call is
# a legitimate heartbeat rather than a mistake.
_TRANSITIONS = {
    "open":            {"claimed", "canceled", "terminated"},
    "claimed":         {"claimed", "in_progress", "creating_report",
                        "submitted", "open", "canceled", "terminated"},
    "in_progress":     {"in_progress", "creating_report", "submitted",
                        "canceled", "terminated"},
    "creating_report": {"creating_report", "submitted", "in_progress",
                        "canceled", "terminated"},
    "submitted":       {"submitted", "reviewing", "in_review", "closed",
                        "rejected", "terminated"},   # self = resubmit
    "reviewing":       {"closed", "rejected", "in_progress", "terminated"},
    "in_review":       {"closed", "rejected", "in_progress", "terminated"},
    "rejected":        {"claimed", "in_progress", "submitted", "canceled",
                        "terminated"},               # fix-and-resubmit, as today
    "closed":          set(),
    "canceled":        set(),
    "terminated":      set(),
}

# 'in_review' predates 'reviewing' in On Board and the ticket tools still
# accept it. Normalising the SOURCE state keeps one row per real state; it
# stays valid as a target so existing callers are unaffected.
_SOURCE_ALIASES = {"in_review": "submitted"}


class TransitionError(RuntimeError):
    """Raised when a requested ticket transition is not permitted."""


def relation(agent_name: str, ticket: dict) -> str:
    """How this agent stands to this ticket: executor, owner, or other.

    Executor dominates when an agent is both, because that is precisely the
    conflict of interest the rules exist to catch.
    """
    if agent_name and ticket.get("claimed_by") == agent_name:
        return "executor"
    if agent_name and ticket.get("created_by") == agent_name:
        return "owner"
    return "other"


def may_claim(agent_name: str, ticket: dict, *, is_coordinator: bool = False) -> bool:
    """Assignment gate: a ticket addressed to someone else is not yours."""
    assigned = ticket.get("assigned_to")
    if not assigned:
        return True                      # unassigned == the open queue
    if assigned == agent_name:
        return True
    return is_coordinator


def _permitted_targets(*, is_owner: bool, is_executor: bool,
                       is_coordinator: bool) -> set:
    """Union of what every hat this agent wears entitles it to.

    Hats stack: an agent that both owns and executed a ticket gets both sets.
    The self-review rule is applied separately, as a stricter overlay, so that
    stacking hats can never launder away the conflict of interest.
    """
    allowed = {"claimed"}                            # anyone joined may take open work
    if is_executor:
        allowed |= EXECUTION_TARGETS | {"open"}      # 'open' = unclaim
    if is_owner or is_coordinator:
        allowed |= ADJUDICATION_TARGETS | CONTROL_TARGETS | {"in_progress"}
    return allowed


def check_transition(current: Optional[str], target: str, *,
                     agent_name: str, ticket: dict,
                     is_coordinator: bool = False,
                     allow_self_review: bool = False) -> str:
    """Raise TransitionError unless this agent may drive this transition.

    :returns: a short basis string ("owner", "coordinator", "executor",
        "queue") suitable for writing into the ticket audit, matching the
        convention already used by _ticket_control_permission.
    """
    current = (current or "open").lower()
    current = _SOURCE_ALIASES.get(current, current)
    if target not in STATES:
        raise TransitionError(f"unknown target state '{target}'")
    if current in TERMINAL:
        raise TransitionError(f"ticket is {current} (terminal); no transitions")
    if target not in _TRANSITIONS.get(current, set()):
        raise TransitionError(f"illegal transition {current} -> {target}")

    is_owner = bool(agent_name) and ticket.get("created_by") == agent_name
    is_executor = bool(agent_name) and ticket.get("claimed_by") == agent_name
    suffix = ""

    # The rule this module exists for. Checked before the entitlement table so
    # the error explains the conflict rather than reading as a generic denial.
    if target in ADJUDICATION_TARGETS and is_executor:
        if not allow_self_review:
            owner = ticket.get("created_by") or "the owner"
            raise TransitionError(
                f"`{agent_name}` executed this ticket and may not also set "
                f"'{target}'. Reaching 'submitted' is the executor's last move "
                f"— completed != success. Ask `{owner}` or a main/lead/reviewer "
                f"agent to review, or pass allow_self_review=True to record an "
                f"unreviewed close in the audit.")
        if not (is_owner or is_coordinator):
            raise TransitionError(
                f"`{agent_name}` neither owns nor coordinates this ticket, so "
                f"allow_self_review does not apply.")
        suffix = " (SELF-REVIEWED — no independent check)"

    if target == "claimed" and not may_claim(agent_name, ticket,
                                             is_coordinator=is_coordinator):
        raise TransitionError(
            f"ticket is assigned to `{ticket.get('assigned_to')}`; "
            f"`{agent_name}` may not claim it")

    permitted = _permitted_targets(is_owner=is_owner, is_executor=is_executor,
                                   is_coordinator=is_coordinator)
    if target not in permitted:
        raise TransitionError(
            f"`{agent_name}` may not set '{target}' on this ticket "
            f"(relation: {relation(agent_name, ticket)}"
            f"{', coordinator' if is_coordinator else ''})")

    if is_owner and is_executor:
        basis = "owner+executor"
    elif is_owner:
        basis = "owner"
    elif is_executor:
        basis = "executor"
    elif is_coordinator:
        basis = "coordinator"
    else:
        basis = "queue"
    return basis + suffix


def can_transition(current: Optional[str], target: str, **kw) -> tuple:
    """Non-raising form, matching _ticket_control_permission's (ok, basis)."""
    try:
        return True, check_transition(current, target, **kw)
    except TransitionError as exc:
        return False, str(exc)
